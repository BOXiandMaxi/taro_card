"""Validate card data, provenance, local WebP files, and optional live database.

Run: backend/.venv/Scripts/python.exe -m database.assets.validate [--offline]
Tracked placeholders are incomplete assets, not ready original artwork.
"""
import argparse
from collections import Counter
from hashlib import sha256
from pathlib import Path
import re
import sys

from database.assets.manifest import (
    ASSET_DIR, PLACEHOLDER_URL, build_manifest, load_manifest, load_provenance, ROOT,
)
from database.seeds.card_meanings import MEANINGS
from database.seeds.reference_data import CARDS, validate_reference_data


TEXT_FIELDS = (
    "upright_description", "reversed_description", "love_meaning",
    "career_meaning", "finance_meaning", "daily_life_meaning",
    "general_guidance_meaning",
)
ALLOWED_LICENSES = {"Public domain", "CC0", "CC BY 4.0", "CC BY-SA 4.0"}


def _hex_digest(value, length):
    return isinstance(value, str) and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None


def rights_error(proof):
    license_name = proof.get("license")
    if license_name not in ALLOWED_LICENSES:
        return "license is not an approved reusable status"
    metadata = proof.get("rights_metadata")
    if not isinstance(metadata, dict):
        return "rights review metadata is missing"
    if (metadata.get("manual_review") == "source page and license checked by importer operator"
            and not proof.get("source_page", "").startswith("https://github.com/mixvlad/TarotCards/")):
        return None
    if metadata.get("mirror_commit"):
        commit = metadata.get("mirror_commit", "")
        if (license_name == "Public domain"
                and _hex_digest(commit, 40)
                and metadata.get("license_doc_url") ==
                f"https://raw.githubusercontent.com/mixvlad/TarotCards/{commit}/SOURCES.md"
                and _hex_digest(metadata.get("license_doc_sha256"), 64)
                and metadata.get("license_statement") == "**License**: Public Domain (copyright expired)"
                and _hex_digest(proof.get("source_sha1"), 40)
                and proof.get("original_url", "").startswith(
                    f"https://raw.githubusercontent.com/mixvlad/TarotCards/{commit}/tarot/rider-waite/720px/"
                )):
            return None
        return "mirror source or license evidence is incomplete"
    if (license_name not in {"Public domain", "CC0"}
            or metadata.get("LicenseShortName") != license_name
            or str(metadata.get("Copyrighted", "")).lower() not in {"", "false"}):
        return "Commons rights metadata does not support the recorded license"
    return None


def validate_assets(check_db=True):
    errors = []
    validate_reference_data()
    expected = build_manifest()
    manifest = load_manifest()
    if manifest != expected:
        errors.append("Manifest differs from 78 stable card/source definitions")
    if set(MEANINGS) != set(range(1, 79)):
        errors.append("Meanings must cover card IDs 1..78 exactly")
    for card_id, row in MEANINGS.items():
        if any(not isinstance(row[key], str) or not row[key].strip() for key in TEXT_FIELDS):
            errors.append(f"Card {card_id}: missing interpretation")
        if any(not any("\u0e00" <= char <= "\u0e7f" for char in row[key]) for key in TEXT_FIELDS):
            errors.append(f"Card {card_id}: interpretation is not readable Thai")
        for key in ("upright_keywords", "reversed_keywords"):
            if not isinstance(row[key], list) or len(row[key]) < 2 or any(not item.strip() for item in row[key]):
                errors.append(f"Card {card_id}: invalid {key}")
    if len(manifest) != 78 or len({item["filename"] for item in manifest}) != 78:
        errors.append("Expected 78 unique asset filenames")
    if len({item["card_id"] for item in manifest}) != 78:
        errors.append("Expected 78 unique manifest card IDs")
    if not (ROOT / "frontend" / "public" / PLACEHOLDER_URL.lstrip("/")).is_file():
        errors.append("Shared development placeholder is missing")
    provenance = load_provenance()
    ready = 0
    tracked_placeholders = 0
    ready_slugs = set()
    for item in manifest:
        path = ASSET_DIR / item["filename"]
        proof = provenance.get(item["slug"])
        if not path.exists():
            if proof:
                errors.append(f"{item['slug']}: provenance exists but WebP file is missing")
            if item.get("placeholder_url") == PLACEHOLDER_URL:
                tracked_placeholders += 1
            else:
                errors.append(f"{item['slug']}: missing artwork has no tracked placeholder")
            continue
        if not proof:
            errors.append(f"{item['slug']}: artwork has no provenance")
            continue
        before_errors = len(errors)
        for key in ("source_page", "license", "artist", "attribution", "verified_at_utc", "sha256"):
            if not proof.get(key):
                errors.append(f"{item['slug']}: missing provenance {key}")
        rights_problem = rights_error(proof)
        if rights_problem:
            errors.append(f"{item['slug']}: {rights_problem}")
        if proof.get("source_page") not in {item["source_page"], item["mirror_source_page"]} or proof.get("filename") != item["filename"]:
            errors.append(f"{item['slug']}: provenance points to another source/file")
        if proof.get("sha256") != sha256(path.read_bytes()).hexdigest():
            errors.append(f"{item['slug']}: WebP checksum mismatch")
        try:
            from PIL import Image
            with Image.open(path) as image:
                image.load()
                if image.format != "WEBP" or image.size != (480, 800):
                    errors.append(f"{item['slug']}: expected 480x800 WebP")
        except ImportError:
            errors.append("Pillow required to decode imported WebP files")
        except Exception as exc:
            errors.append(f"{item['slug']}: invalid image ({exc})")
        if len(errors) == before_errors:
            ready += 1
            ready_slugs.add(item["slug"])
    extra_files = {path.name for path in ASSET_DIR.glob("*.webp")} - {item["filename"] for item in manifest}
    if extra_files:
        errors.append(f"Untracked WebP files: {', '.join(sorted(extra_files))}")
    if check_db:
        _validate_database(manifest, ready_slugs, errors)
    return {"ready": ready, "incomplete": 78 - ready,
            "tracked_placeholders": tracked_placeholders, "errors": errors}


def _validate_database(manifest, ready_slugs, errors):
    sys.path.insert(0, str(ROOT / "backend"))
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app.database.session import get_engine
    from app.models import CardMeaning, TarotCard
    with Session(get_engine()) as session:
        cards = session.scalars(select(TarotCard).order_by(TarotCard.id)).all()
        meanings = session.scalars(select(CardMeaning)).all()
        if len(cards) != 78 or [card.id for card in cards] != list(range(1, 79)):
            errors.append("Database must contain exactly 78 stable cards")
        if len(meanings) != 78 or Counter(row.card_id for row in meanings) != Counter(range(1, 79)):
            errors.append("Database must contain one valid meaning reference per card")
        by_id = {card.id: card for card in cards}
        for item in manifest:
            card = by_id.get(item["card_id"])
            if card is None:
                continue
            reference = CARDS[item["card_id"] - 1]
            if (card.slug, card.name_en, card.name_th, card.arcana, card.suit, card.rank) != (
                reference["slug"], reference["name_en"], reference["name_th"],
                reference["arcana"], reference["suit"], reference["rank"]
            ):
                errors.append(f"Database card metadata mismatch: {card.id}")
            if card.image_filename != item["filename"]:
                errors.append(f"Database image filename mismatch: {card.id}")
            if card.slug in ready_slugs:
                if card.image_path != item["asset_url"]:
                    errors.append(f"Database image path not linked: {card.id}")
            elif card.image_path is not None:
                errors.append(f"Database path points to incomplete artwork: {card.id}")
        for meaning in meanings:
            if meaning.card_id not in MEANINGS:
                errors.append(f"Broken meaning card reference: {meaning.card_id}")
            elif any(not getattr(meaning, key) for key in TEXT_FIELDS):
                errors.append(f"Database meaning incomplete: {meaning.card_id}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Skip live database checks")
    args = parser.parse_args()
    result = validate_assets(check_db=not args.offline)
    print(f"Ready original assets: {result['ready']}/78")
    print(f"Incomplete assets: {result['incomplete']}/78 (tracked placeholders: {result['tracked_placeholders']})")
    print(f"Card meanings: {len(MEANINGS)}/78")
    for error in result["errors"]:
        print("ERROR:", error)
    if result["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
