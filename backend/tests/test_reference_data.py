import unittest

from database.seeds.reference_data import (
    CARDS, CATEGORIES, QUESTIONS, SPREADS, POSITIONS, validate_reference_data,
)
from database.seeds.card_meanings import MEANINGS
from database.assets.manifest import build_manifest, load_manifest
from database.assets.validate import rights_error


class ReferenceDataTests(unittest.TestCase):
    def test_deck_invariants(self):
        validate_reference_data()
        self.assertEqual(len(CARDS), 78)
        self.assertEqual(len({card["id"] for card in CARDS}), 78)
        self.assertEqual(len({card["slug"] for card in CARDS}), 78)
        self.assertEqual(sum(card["arcana"] == "major" for card in CARDS), 22)
        self.assertEqual(sum(card["arcana"] == "minor" for card in CARDS), 56)

    def test_rws_numbering(self):
        by_slug = {card["slug"]: card for card in CARDS}
        self.assertEqual(by_slug["the-fool"]["rank"], 0)
        self.assertEqual(by_slug["strength"]["rank"], 8)
        self.assertEqual(by_slug["justice"]["rank"], 11)
        self.assertEqual(CARDS[-1]["slug"], "king-of-pentacles")
        self.assertEqual(CARDS[-1]["id"], 78)

    def test_suit_distribution(self):
        for suit in ("wands", "cups", "swords", "pentacles"):
            with self.subTest(suit=suit):
                ranks = [card["rank"] for card in CARDS if card["suit"] == suit]
                self.assertEqual(sorted(ranks), list(range(1, 15)))

    def test_artwork_is_not_claimed(self):
        self.assertTrue(all(card["image_path"] is None for card in CARDS))
        self.assertEqual(len({card["image_filename"] for card in CARDS}), 78)
        self.assertEqual(load_manifest(), build_manifest())

    def test_meanings_cover_deck_with_distinct_thai_text(self):
        self.assertEqual(set(MEANINGS), set(range(1, 79)))
        for field in ("upright_description", "reversed_description", "love_meaning",
                      "career_meaning", "finance_meaning", "daily_life_meaning",
                      "general_guidance_meaning"):
            self.assertEqual(len({row[field] for row in MEANINGS.values()}), 78)
            self.assertTrue(all(any("\u0e00" <= char <= "\u0e7f" for char in row[field])
                                for row in MEANINGS.values()))

    def test_asset_rights_gate_rejects_unapproved_license(self):
        self.assertIsNotNone(rights_error({"license": "All rights reserved", "rights_metadata": {
            "manual_review": "source page and license checked by importer operator",
        }}))
        self.assertIsNone(rights_error({"license": "Public domain", "rights_metadata": {
            "LicenseShortName": "Public domain", "Copyrighted": "False",
        }}))

    def test_supplied_questions(self):
        self.assertEqual(len(CATEGORIES), 5)
        self.assertEqual(len(QUESTIONS), 32)
        self.assertEqual(len({q["id"] for q in QUESTIONS}), 32)
        self.assertEqual(len({q["prompt_th"] for q in QUESTIONS}), 32)
        self.assertEqual(QUESTIONS[0]["prompt_th"], "วันนี้มีอะไรที่ควรใส่ใจ?")
        self.assertEqual(QUESTIONS[29]["prompt_th"], "คำแนะนำจากไพ่")
        self.assertEqual((QUESTIONS[30]["category_id"], QUESTIONS[30]["display_order"], QUESTIONS[30]["prompt_th"]),
                         (3, 7, "เขาคนนั้นกำลังคิดอย่างไรกับเรา?"))
        self.assertEqual((QUESTIONS[31]["category_id"], QUESTIONS[31]["display_order"], QUESTIONS[31]["prompt_th"]),
                         (4, 7, "เราจะได้งานใหม่เมื่อไร?"))

    def test_spread_ordering(self):
        self.assertEqual([s["card_count"] for s in SPREADS], [3, 5, 10])
        self.assertEqual(len(POSITIONS), 18)
        for spread in SPREADS:
            numbers = [p["position_number"] for p in POSITIONS if p["spread_id"] == spread["id"]]
            self.assertEqual(numbers, list(range(1, spread["card_count"] + 1)))

    def test_validation_rejects_duplicate_card(self):
        original = CARDS[-1]
        try:
            CARDS[-1] = dict(CARDS[0])
            with self.assertRaises(ValueError):
                validate_reference_data()
        finally:
            CARDS[-1] = original
