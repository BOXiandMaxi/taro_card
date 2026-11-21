"""Stable RWS metadata, supplied Thai questions, and documented default spreads.

Expected filenames do not assert that the artwork has been imported or verified.
"""

MAJOR = (
    ("the-fool", "The Fool", "ผู้เริ่มต้น"),
    ("the-magician", "The Magician", "นักมายากล"),
    ("the-high-priestess", "The High Priestess", "มหาปุโรหิตหญิง"),
    ("the-empress", "The Empress", "จักรพรรดินี"),
    ("the-emperor", "The Emperor", "จักรพรรดิ"),
    ("the-hierophant", "The Hierophant", "มหาปุโรหิต"),
    ("the-lovers", "The Lovers", "คู่รัก"),
    ("the-chariot", "The Chariot", "รถศึก"),
    ("strength", "Strength", "ความเข้มแข็ง"),
    ("the-hermit", "The Hermit", "ฤๅษี"),
    ("wheel-of-fortune", "Wheel of Fortune", "วงล้อแห่งโชคชะตา"),
    ("justice", "Justice", "ความยุติธรรม"),
    ("the-hanged-man", "The Hanged Man", "ชายผู้ห้อยหัว"),
    ("death", "Death", "ความตาย"),
    ("temperance", "Temperance", "ความพอดี"),
    ("the-devil", "The Devil", "ปีศาจ"),
    ("the-tower", "The Tower", "หอคอย"),
    ("the-star", "The Star", "ดวงดาว"),
    ("the-moon", "The Moon", "ดวงจันทร์"),
    ("the-sun", "The Sun", "ดวงอาทิตย์"),
    ("judgement", "Judgement", "การตื่นรู้"),
    ("the-world", "The World", "โลก"),
)
SUITS = (("wands", "ไม้เท้า"), ("cups", "ถ้วย"), ("swords", "ดาบ"), ("pentacles", "เหรียญ"))
RANKS = (
    ("ace", "Ace", "หนึ่ง"), ("two", "Two", "สอง"), ("three", "Three", "สาม"),
    ("four", "Four", "สี่"), ("five", "Five", "ห้า"), ("six", "Six", "หก"),
    ("seven", "Seven", "เจ็ด"), ("eight", "Eight", "แปด"), ("nine", "Nine", "เก้า"),
    ("ten", "Ten", "สิบ"), ("page", "Page", "มหาดเล็ก"), ("knight", "Knight", "อัศวิน"),
    ("queen", "Queen", "ราชินี"), ("king", "King", "ราชา"),
)

CARDS = [
    dict(id=rank + 1, slug=slug, name_en=name_en, name_th=name_th,
         arcana="major", suit=None, rank=rank, image_filename=f"{slug}.webp", image_path=None)
    for rank, (slug, name_en, name_th) in enumerate(MAJOR)
]
for suit_index, (suit, suit_th) in enumerate(SUITS):
    for rank, (rank_slug, rank_en, rank_th) in enumerate(RANKS, 1):
        CARDS.append(dict(
            id=23 + suit_index * 14 + rank - 1, slug=f"{rank_slug}-of-{suit}",
            name_en=f"{rank_en} of {suit.title()}", name_th=f"{rank_th}{suit_th}",
            arcana="minor", suit=suit, rank=rank,
            image_filename=f"{rank_slug}-of-{suit}.webp", image_path=None,
        ))

CATEGORY_QUESTIONS = (
    ("daily-life", "ชีวิตประจำวัน", (
        "วันนี้มีอะไรที่ควรใส่ใจ?", "สัปดาห์นี้มีแนวโน้มอย่างไร?",
        "สิ่งที่ควรระวังในช่วงนี้", "อุปสรรคที่กำลังเผชิญ",
        "สิ่งที่ควรเปลี่ยนแปลง", "คำแนะนำประจำเดือน",
    )),
    ("finance", "การเงิน", (
        "สถานการณ์การเงินปัจจุบัน", "โอกาสเพิ่มรายได้", "ความเสี่ยงด้านการเงิน",
        "สิ่งที่ควรพิจารณาก่อนลงทุน", "อุปสรรคทางการเงิน", "การวางแผนการเงินในอนาคต",
    )),
    ("love", "ความรัก", (
        "ความรักของคนโสด", "ความสัมพันธ์ปัจจุบัน", "สิ่งที่ควรปรับปรุงในความสัมพันธ์",
        "การเริ่มต้นความรักครั้งใหม่", "บทเรียนจากความรักในอดีต", "คำแนะนำด้านความรัก",
    )),
    ("career", "การงาน", (
        "สถานการณ์การงานปัจจุบัน", "สิ่งที่ควรพิจารณาก่อนเปลี่ยนงาน", "โอกาสเติบโตในอาชีพ",
        "ความสัมพันธ์กับเพื่อนร่วมงาน", "อุปสรรคในการทำงาน", "การเตรียมพร้อมสำหรับงานใหม่",
    )),
    ("guidance", "ไพ่อยากบอกอะไรกับเรา", (
        "ข้อความที่ควรรับฟัง", "สิ่งที่กำลังมองข้าม", "บทเรียนสำคัญในชีวิต",
        "สิ่งที่ควรปล่อยวาง", "จุดแข็งที่ยังไม่ค้นพบ", "คำแนะนำจากไพ่",
    )),
)
CATEGORIES = [dict(id=i, slug=slug, name_th=name) for i, (slug, name, _) in enumerate(CATEGORY_QUESTIONS, 1)]
QUESTIONS = [
    dict(id=(category_id - 1) * 6 + order, category_id=category_id,
         prompt_th=prompt, display_order=order, recommended_spread_id=None)
    for category_id, (_, _, prompts) in enumerate(CATEGORY_QUESTIONS, 1)
    for order, prompt in enumerate(prompts, 1)
]
QUESTIONS.extend((
    dict(id=31, category_id=3, prompt_th="เขาคนนั้นกำลังคิดอย่างไรกับเรา?",
         display_order=7, recommended_spread_id=None),
    dict(id=32, category_id=4, prompt_th="เราจะได้งานใหม่เมื่อไร?",
         display_order=7, recommended_spread_id=None),
))

SPREAD_DEFINITIONS = (
    ("three-card", "ไพ่ 3 ใบ", ("สถานการณ์ปัจจุบัน", "อุปสรรคหรืออิทธิพลหลัก", "คำแนะนำ")),
    ("five-card", "ไพ่ 5 ใบ", (
        "สถานการณ์ปัจจุบัน", "สาเหตุที่เป็นรากฐาน", "อุปสรรคหลัก",
        "จุดแข็งและทรัพยากรที่มี", "คำแนะนำและแนวทางที่เป็นไปได้",
    )),
    ("celtic-cross", "เซลติกครอส 10 ใบ", (
        "สถานการณ์ปัจจุบัน", "อิทธิพลที่เข้ามาขวาง", "เป้าหมายที่ตระหนักรู้",
        "รากฐานของสถานการณ์", "อดีตที่ผ่านมาไม่นาน", "อนาคตอันใกล้",
        "มุมมองต่อตนเอง", "สภาพแวดล้อมรอบตัว", "ความหวังและความกลัว", "ทิศทางที่เป็นไปได้",
    )),
)
SPREADS = [dict(id=i, slug=slug, name_th=name, card_count=len(positions))
           for i, (slug, name, positions) in enumerate(SPREAD_DEFINITIONS, 1)]
POSITIONS = []
for spread_id, (_, _, meanings) in enumerate(SPREAD_DEFINITIONS, 1):
    for number, meaning in enumerate(meanings, 1):
        POSITIONS.append(dict(id=len(POSITIONS) + 1, spread_id=spread_id,
                              position_number=number, meaning_th=meaning))


def validate_reference_data():
    """Explicit errors remain enabled under python -O."""
    if len(CARDS) != 78 or {c["id"] for c in CARDS} != set(range(1, 79)):
        raise ValueError("Expected exactly 78 stable card IDs")
    if len({c["slug"] for c in CARDS}) != 78:
        raise ValueError("Duplicate card slug")
    if len({c["image_filename"] for c in CARDS}) != 78:
        raise ValueError("Duplicate image filename")
    if sum(c["arcana"] == "major" for c in CARDS) != 22:
        raise ValueError("Expected 22 Major Arcana")
    for suit, _ in SUITS:
        cards = [c for c in CARDS if c["arcana"] == "minor" and c["suit"] == suit]
        if len(cards) != 14 or {c["rank"] for c in cards} != set(range(1, 15)):
            raise ValueError(f"Invalid suit: {suit}")
    if len(CATEGORIES) != 5 or len(QUESTIONS) != 32 or {q["id"] for q in QUESTIONS} != set(range(1, 33)):
        raise ValueError("Expected five categories and 32 stable questions")
    for category in CATEGORIES:
        orders = [q["display_order"] for q in QUESTIONS if q["category_id"] == category["id"]]
        expected_count = 7 if category["slug"] in {"love", "career"} else 6
        if sorted(orders) != list(range(1, expected_count + 1)):
            raise ValueError("Invalid question order")
    for spread in SPREADS:
        numbers = [p["position_number"] for p in POSITIONS if p["spread_id"] == spread["id"]]
        if sorted(numbers) != list(range(1, spread["card_count"] + 1)):
            raise ValueError("Invalid spread positions")
