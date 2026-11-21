"""Import 1910 RWS artwork from Wikimedia Commons or reviewed local files.

Requires Pillow. Run from project root: python -m database.assets.import_rws --help
No network is needed for import-local; download checks each Commons file's rights.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha1, sha256
from html import unescape
from io import BytesIO
import json
from pathlib import Path
import re
import tempfile
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from database.assets.manifest import ASSET_DIR, PROVENANCE_PATH, load_manifest, load_provenance
from database.seeds.reference_data import CARDS


API = "https://commons.wikimedia.org/w/api.php"
SIZE = (480, 800)
MAX_SOURCE_BYTES = 20_000_000
USER_AGENT = "TarotReading-RWS-asset-import/1.0 (Wikimedia Commons source attribution)"
MIRROR_REPO = "https://api.github.com/repos/mixvlad/TarotCards"
MIRROR_RAW = "https://raw.githubusercontent.com/mixvlad/TarotCards"


def _plain(value):
    return unescape(re.sub(r"<[^>]*>", "", str(value) if value is not None else "")).strip()


def _write_json_atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", dir=path.parent, delete=False) as temp:
        json.dump(value, temp, ensure_ascii=False, indent=2, sort_keys=True)
        temp.write("\n")
        temp_path = Path(temp.name)
    temp_path.replace(path)


def _make_webp(content, destination):
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError("Install Pillow before importing artwork") from exc
    with Image.open(BytesIO(content)) as source:
        source.load()
        if source.width < 400 or source.height < 650 or source.height <= source.width:
            raise ValueError("Source must be a high-resolution portrait card scan")
        image = ImageOps.contain(source.convert("RGB"), SIZE, method=Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", SIZE, "#eee8dc")
    canvas.paste(image, ((SIZE[0] - image.width) // 2, (SIZE[1] - image.height) // 2))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".webp", dir=destination.parent, delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        canvas.save(temp_path, format="WEBP", quality=82, method=6)
        with Image.open(temp_path) as check:
            check.load()
            if check.format != "WEBP" or check.size != SIZE:
                raise ValueError("WebP conversion failed validation")
        digest = sha256(temp_path.read_bytes()).hexdigest()
        temp_path.replace(destination)
        return digest
    finally:
        temp_path.unlink(missing_ok=True)


def _api_info(entry):
    query = urlencode({
        "action": "query", "format": "json", "prop": "imageinfo",
        "titles": "File:" + entry["source_file_title"],
        "iiprop": "url|sha1|extmetadata",
    })
    request = Request(API + "?" + query, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        result = json.load(response)
    pages = result["query"]["pages"]
    page = next(iter(pages.values()))
    if "missing" in page or not page.get("imageinfo"):
        raise ValueError(f"Commons file missing: {entry['source_file_title']}")
    info = page["imageinfo"][0]
    meta = {key: _plain(value.get("value")) for key, value in info.get("extmetadata", {}).items()}
    license_name = meta.get("LicenseShortName", "")
    copyrighted = meta.get("Copyrighted", "").lower()
    if license_name.lower() not in {"public domain", "cc0"} or copyrighted not in {"", "false"}:
        raise ValueError(f"Rights require manual review: {entry['source_file_title']} ({license_name})")
    source_url = info["url"]
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname != "upload.wikimedia.org":
        raise ValueError("Unexpected download host")
    return info, meta


def _download_bytes(url):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        content = response.read(MAX_SOURCE_BYTES + 1)
    if len(content) > MAX_SOURCE_BYTES:
        raise ValueError("Source file exceeds size limit")
    return content


def _mirror_evidence():
    with urlopen(Request(MIRROR_REPO + "/commits/main", headers={"User-Agent": USER_AGENT}), timeout=30) as response:
        commit = json.load(response)["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid mirror commit")
    document_url = f"{MIRROR_RAW}/{commit}/SOURCES.md"
    document = _download_bytes(document_url)
    section = document.decode("utf-8").split("## Rider-Waite Tarot Deck", 1)[1].split("## Soimoi Tarot Deck", 1)[0]
    license_statement = "**License**: Public Domain (copyright expired)"
    if license_statement not in section or "Pamela Colman Smith" not in section or "Steve P." not in section:
        raise ValueError("Mirror source document does not verify the stated deck and license")
    return commit, {
        "mirror_commit": commit,
        "license_doc_url": document_url,
        "license_doc_sha256": sha256(document).hexdigest(),
        "license_statement": license_statement,
        "scan_restoration": "Steve P. (steve-p.org)",
    }


def _record(entry, content, metadata, *, license_name, attribution, original_url, source_sha1=None, source_page=None):
    destination = ASSET_DIR / entry["filename"]
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite {destination}")
    digest = _make_webp(content, destination)
    provenance = load_provenance()
    provenance[entry["slug"]] = {
        "card_id": entry["card_id"], "filename": entry["filename"],
        "source_page": source_page or entry["source_page"], "original_url": original_url,
        "artist": entry["artist"], "edition": entry["edition"],
        "license": license_name, "attribution": attribution,
        "source_sha1": source_sha1, "sha256": digest,
        "width": SIZE[0], "height": SIZE[1],
        "verified_at_utc": datetime.now(timezone.utc).isoformat(),
        "rights_metadata": metadata,
    }
    try:
        _write_json_atomic(PROVENANCE_PATH, provenance)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    print(f"Imported {entry['filename']}")


def download(entries):
    for entry in entries:
        if (ASSET_DIR / entry["filename"]).exists():
            if entry["slug"] not in load_provenance():
                raise ValueError(f"Existing file has no provenance: {entry['filename']}")
            print(f"Already present: {entry['filename']}")
            continue
        info, meta = _api_info(entry)
        content = _download_bytes(info["url"])
        if info.get("sha1") and sha1(content).hexdigest() != info["sha1"]:
            raise ValueError(f"Source checksum mismatch: {entry['source_file_title']}")
        _record(entry, content, meta, license_name=meta["LicenseShortName"],
                attribution=meta.get("Attribution", "") or entry["artist"],
                original_url=info["url"], source_sha1=info.get("sha1"))


def download_mirror(entries):
    """Import the documented public-domain Pam-A scans when Commons image hosting is unavailable."""
    from database.assets.manifest import mirror_filename
    cards_by_id = {card["id"]: card for card in CARDS}
    commit, metadata = _mirror_evidence()
    for entry in entries:
        if (ASSET_DIR / entry["filename"]).exists():
            if entry["slug"] not in load_provenance():
                raise ValueError(f"Existing file has no provenance: {entry['filename']}")
            print(f"Already present: {entry['filename']}", flush=True)
            continue
        card = cards_by_id[entry["card_id"]]
        name = mirror_filename(card)
        url = f"{MIRROR_RAW}/{commit}/tarot/rider-waite/720px/{name}"
        content = _download_bytes(url)
        _record(entry, content, metadata, license_name="Public domain",
                attribution="Pamela Colman Smith; scan restoration Steve P.",
                original_url=url, source_sha1=sha1(content).hexdigest(),
                source_page=entry["mirror_source_page"])


def verify_mirror(entries):
    """Recheck existing mirror-derived WebP files against a pinned source and rights document."""
    from database.assets.manifest import mirror_filename
    commit, metadata = _mirror_evidence()
    cards_by_id = {card["id"]: card for card in CARDS}
    provenance = load_provenance()
    with tempfile.TemporaryDirectory() as directory:
        for entry in entries:
            proof = provenance.get(entry["slug"])
            destination = ASSET_DIR / entry["filename"]
            if not proof or not destination.is_file() or proof.get("source_page") != entry["mirror_source_page"]:
                raise ValueError(f"Missing mirror artwork/provenance: {entry['slug']}")
            name = mirror_filename(cards_by_id[entry["card_id"]])
            url = f"{MIRROR_RAW}/{commit}/tarot/rider-waite/720px/{name}"
            content = _download_bytes(url)
            digest = _make_webp(content, Path(directory) / entry["filename"])
            if digest != proof.get("sha256") or digest != sha256(destination.read_bytes()).hexdigest():
                raise ValueError(f"Mirror source does not match imported WebP: {entry['slug']}")
            proof.update(original_url=url, source_sha1=sha1(content).hexdigest(),
                         rights_metadata=metadata,
                         verified_at_utc=datetime.now(timezone.utc).isoformat())
            print(f"Verified {entry['filename']}", flush=True)
    _write_json_atomic(PROVENANCE_PATH, provenance)


def import_local(entry, source, license_name, attribution):
    if license_name not in {"Public domain", "CC0", "CC BY 4.0", "CC BY-SA 4.0"}:
        raise ValueError("Supply a reviewed license: Public domain, CC0, CC BY 4.0, or CC BY-SA 4.0")
    if not attribution.strip():
        raise ValueError("Attribution/creator must be recorded")
    content = source.read_bytes()
    if len(content) > MAX_SOURCE_BYTES:
        raise ValueError("Source file exceeds size limit")
    _record(entry, content, {"manual_review": "source page and license checked by importer operator"},
            license_name=license_name, attribution=attribution.strip(), original_url=entry["source_page"])


def sync_db():
    from database.assets.validate import validate_assets
    result = validate_assets(check_db=False)
    if result["ready"] != 78 or result["errors"]:
        raise ValueError("All 78 verified local images are required before database sync")
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
    from sqlalchemy.orm import Session
    from app.database.session import get_engine
    from app.models import TarotCard
    with Session(get_engine()) as session, session.begin():
        for entry in load_manifest():
            card = session.get(TarotCard, entry["card_id"])
            if card is None or card.slug != entry["slug"] or card.image_filename != entry["filename"]:
                raise ValueError(f"Database card identity mismatch: {entry['card_id']}")
            if card.image_path not in (None, entry["asset_url"]):
                raise ValueError(f"Refusing to replace edited image path: {entry['slug']}")
            card.image_path = entry["asset_url"]
    print("Linked 78 verified local WebP files in database")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("download", help="Download and verify each Commons source before WebP conversion")
    commands.add_parser("download-mirror", help="Download documented public-domain Pam-A scans from GitHub mirror")
    commands.add_parser("verify-mirror", help="Pin and recheck imported mirror scans against source and license document")
    manual = commands.add_parser("import-local", help="Import one manually reviewed source scan")
    manual.add_argument("slug")
    manual.add_argument("source", type=Path)
    manual.add_argument("--license", required=True)
    manual.add_argument("--attribution", required=True)
    commands.add_parser("sync-db", help="Link image paths only after all 78 files validate")
    args = parser.parse_args()
    entries = load_manifest()
    if args.command == "download":
        download(entries)
    elif args.command == "download-mirror":
        download_mirror(entries)
    elif args.command == "verify-mirror":
        verify_mirror(entries)
    elif args.command == "import-local":
        entry = next((item for item in entries if item["slug"] == args.slug), None)
        if entry is None:
            parser.error("Unknown card slug")
        import_local(entry, args.source, args.license, args.attribution)
    else:
        sync_db()


if __name__ == "__main__":
    main()
