"""Expected 1910 Pamela-A scans listed by Wikimedia Commons.

Source page titles are candidates. Their individual rights must be checked by
the importer before an image is treated as ready artwork.
"""
import json
from pathlib import Path
from urllib.parse import quote

from database.seeds.reference_data import CARDS


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = Path(__file__).with_name("rws_manifest.json")
PROVENANCE_PATH = Path(__file__).with_name("verified_provenance.json")
ASSET_DIR = ROOT / "frontend" / "public" / "assets" / "cards" / "rws"
ASSET_URL_PREFIX = "/assets/cards/rws/"
PLACEHOLDER_URL = "/assets/cards/card-placeholder.svg"

MAJOR_TITLES = (
    "The Fool", "The Magician", "The High Priestess", "The Empress",
    "The Emperor", "The Hierophant", "The Lovers", "The Chariot",
    "Strength", "The Hermit", "Wheel of Fortune", "Justice",
    "The Hanged Man", "Death", "Temperance", "The Devil",
    "The Tower", "The Star", "The Moon", "The Sun", "Judgement",
    "The World",
)
COURT_TITLES = {1: "Ace", 11: "Page", 12: "Knight", 13: "Queen", 14: "King"}


def source_title(card):
    if card["arcana"] == "major":
        return f"RWS Tarot 1910 - {card['rank']:02d} {MAJOR_TITLES[card['rank']]}.png"
    suit = card["suit"].title()
    rank = card["rank"]
    suffix = f" ({COURT_TITLES[rank]})" if rank in COURT_TITLES else ""
    return f"RWS Tarot 1910 - {suit} {rank:02d}{suffix}.png"


def mirror_filename(card):
    if card["arcana"] == "major":
        return f"{card['rank']:02d}_{MAJOR_TITLES[card['rank']].replace('The ', '').replace(' ', '_')}.jpg"
    suit = "Pents" if card["suit"] == "pentacles" else card["suit"].title()
    return f"{suit}{card['rank']:02d}.jpg"


def build_manifest():
    entries = []
    for card in CARDS:
        title = source_title(card)
        entries.append({
            "card_id": card["id"],
            "slug": card["slug"],
            "filename": card["image_filename"],
            "asset_url": ASSET_URL_PREFIX + card["image_filename"],
            "placeholder_url": PLACEHOLDER_URL,
            "source_file_title": title,
            "source_page": "https://commons.wikimedia.org/wiki/File:" + quote(title.replace(" ", "_"), safe="()_-"),
            "mirror_source_page": "https://github.com/mixvlad/TarotCards/blob/main/tarot/rider-waite/720px/" + mirror_filename(card),
            "artist": "Pamela Colman Smith",
            "edition": "1910 Rider-Waite-Smith Pamela-A",
            "license_status": "pending-per-file-verification",
        })
    return entries


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def load_provenance():
    if not PROVENANCE_PATH.exists():
        return {}
    return json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    MANIFEST_PATH.write_text(json.dumps(build_manifest(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(build_manifest())} expected source records")
