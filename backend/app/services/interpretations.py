from collections import Counter
from dataclasses import replace
from datetime import timedelta
from time import sleep

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings
from app.database.base import utc_now
from app.database.session import start_write
from app.models import (
    AIUsageLog, Category, Question, Reading, ReadingCard, ReadingInterpretation, SpreadPosition, TarotCard, TarotSpread,
)
from app.services.interpretation_provider import Provider
from app.services.interpretation_schema import (
    CardIdentity, CardInterpretation, FixedCard, InterpretationInput, InterpretationResult,
)

ATTEMPTS = 2
# Longer than both maximum provider timeouts and the retry delay.
CLAIM_MAX_AGE = timedelta(minutes=2)
CATEGORY_MEANING_FIELDS = {
    "daily-life": "daily_life_meaning",
    "finance": "finance_meaning",
    "love": "love_meaning",
    "career": "career_meaning",
    "guidance": "general_guidance_meaning",
}
CATEGORY_ACTIONS = {
    "daily-life": "เลือกเรื่องที่จัดการได้วันนี้หนึ่งเรื่อง แล้วกันเวลาให้ขั้นแรก",
    "finance": "จดตัวเลขและเงื่อนไขที่เกี่ยวกับคำถาม แล้ววงข้อมูลที่ต้องตรวจสอบก่อนตัดสินใจ",
    "love": "จดสิ่งที่สังเกตได้และสิ่งที่อยากถาม หากพร้อมคุยให้เริ่มจากคำถามปลายเปิดหนึ่งข้อ",
    "career": "จดตัวอย่างจากงานจริงหนึ่งเหตุการณ์ที่ช่วยตอบคำถาม แล้วระบุข้อมูลที่ยังขาด",
    "guidance": "เขียนสิ่งที่ควบคุมได้หนึ่งอย่าง แล้วเลือกวิธีทดลองทำในสัปดาห์นี้",
}
CATEGORY_SUMMARIES = {
    "daily-life": "เริ่มจากเรื่องที่กินแรงหรือเวลาของคุณมากที่สุด แล้วดูว่ามีส่วนไหนที่จัดการได้ตอนนี้",
    "finance": "ก่อนตัดสินใจเรื่องเงิน ให้แยกสิ่งที่เกิดขึ้นจริงจากสิ่งที่คาดไว้ โดยเฉพาะรายรับ รายจ่าย และเงื่อนไขที่ยังไม่ชัด",
    "love": "ลองดูว่าคำพูดและการกระทำที่เกิดขึ้นจริงตรงกับสิ่งที่คุณต้องการจากความสัมพันธ์แค่ไหน",
    "career": "ลองแยกเรื่องที่คุณปรับเองได้ออกจากเรื่องที่ต้องตกลงกับคนอื่น จะได้เห็นว่าควรเริ่มตรงไหน",
    "guidance": "ลองมองหาสิ่งที่เกิดซ้ำในเรื่องนี้ เพราะอาจช่วยให้เห็นว่าควรเปลี่ยนอะไรทีละอย่าง",
}
CAREER_QUESTION_GUIDANCE = (
    ("เปลี่ยนงาน", "ถ้ากำลังชั่งใจว่าจะเปลี่ยนงานไหม ให้เริ่มจากดูว่างานใหม่แก้ปัญหาที่อยากออกจากงานเดิมได้จริงหรือเปล่า",
     "เทียบงานปัจจุบันกับงานที่สนใจในเรื่องหน้าที่ เวลา และรายได้ แล้วตรวจข้อมูลที่ยังไม่ชัด"),
    ("เติบโต", "ถ้าอยากเติบโตในงาน ลองมองหาทักษะที่ได้ใช้กับงานจริงและเห็นความคืบหน้าได้",
     "เลือกทักษะหนึ่งอย่าง แล้วถามว่ามีงานชิ้นไหนให้ลองฝึกและขอคำแนะนำได้"),
    ("เพื่อนร่วมงาน", "เรื่องเพื่อนร่วมงานอาจเริ่มแก้ได้จากการคุยกันให้ชัดว่าแต่ละฝ่ายคาดหวังอะไร",
     "เลือกเหตุการณ์ล่าสุดหนึ่งครั้ง แล้วถามถึงข้อตกลงที่อยากให้ชัดขึ้น เช่น ใครทำอะไรและส่งเมื่อไหร่"),
)
TIMING_CUES = ("เมื่อไร", "เมื่อไหร่", "ตอนไหน", "ช่วงไหน", "เดือนไหน", "นานแค่ไหน", "อีกนานไหม", "กี่วัน", "กี่เดือน", "กี่ปี")
JOB_SEARCH_CUES = ("งานใหม่", "สมัครงาน", "หางาน", "สัมภาษณ์งาน", "เปลี่ยนงาน")
JOB_OFFER_CUES = ("ได้งาน", "จะได้เริ่มงาน", "ข้อเสนองาน", "ผลสัมภาษณ์")
PLAIN_TOPICS = {
    "หมุนหลายอย่าง": "การแบ่งเวลาให้หลายเรื่องพร้อมกัน",
    "โครงสร้าง": "กติกาและหน้าที่ที่ต้องรับผิดชอบ",
    "เหตุผล": "เกณฑ์ที่ใช้ตัดสินใจ",
    "แลกเปลี่ยน": "ความร่วมมือที่ดีต่อทั้งสองฝ่าย",
    "พันธนาการ": "ข้อผูกมัดที่ทำให้ขยับตัวลำบาก",
}
SYNTHESIS_TOPICS = {
    **PLAIN_TOPICS,
    "หลักการ": "การตั้งเกณฑ์ให้ชัด",
    "แข็งกร้าว": "การยึดเกณฑ์จนปรับตัวได้ยาก",
    "เย็นชา": "การมองข้ามมุมของคนอื่น",
    "หลุดพ้น": "การค่อย ๆ คลายสิ่งที่รั้งไว้",
    "เข้าใจคลาด": "ความเข้าใจที่ยังไม่ตรงกัน",
    "เริ่มต้น": "การลองทางใหม่",
    "หุนหัน": "ความรีบจนเตรียมตัวไม่ทัน",
    "ลงมือทำ": "การใช้สิ่งที่มีให้เกิดผล",
    "กระจัดกระจาย": "ความสนใจที่ถูกดึงไปหลายทาง",
    "สัญชาตญาณ": "สิ่งที่ยังไม่มีคำตอบชัด",
    "คลุมเครือ": "สิ่งที่ยังไม่มีคำตอบชัด",
    "สับสน": "ความกังวลที่ทำให้มองสถานการณ์ไม่ชัด",
    "พักฟื้น": "การพักให้พอแล้วค่อยกลับมาลงมือ",
    "หวัง": "การค่อย ๆ กลับมามีแรง",
    "ขอความช่วยเหลือ": "การขอแรงจากคนอื่น",
    "ร่วมมือ": "การขอแรงจากคนอื่น",
    "ยุติธรรม": "การดูข้อมูลจากทั้งสองฝ่าย",
    "ลำเอียง": "การให้น้ำหนักกับข้อมูลบางด้านมากเกินไป",
    "คำสอน": "ข้อแนะนำจากคนที่มีประสบการณ์",
}
SYNTHESIS_QUESTIONS = {
    "daily-life": "เรื่องที่คุณกำลังเจอวันนี้",
    "finance": "การตัดสินใจเรื่องเงิน",
    "love": "ความสัมพันธ์ครั้งนี้",
    "career": "เรื่องงานนี้",
    "guidance": "คำถามนี้",
}


def revealed_positions(reading: Reading, spread: TarotSpread) -> list[tuple[SpreadPosition, ReadingCard]] | None:
    cards_by_position = {card.position_id: card for card in reading.cards}
    if (
        spread.card_count not in (3, 5, 10)
        or [position.position_number for position in spread.positions] != list(range(1, spread.card_count + 1))
        or cards_by_position.keys() != {position.id for position in spread.positions}
        or any(card.revealed_at is None for card in reading.cards)
    ):
        return None
    return [(position, cards_by_position[position.id]) for position in spread.positions]


def _excerpt(value: str | None, limit: int) -> str:
    value = (value or "").strip()
    return value if len(value) <= limit else f"{value[:limit - 1].rstrip()}…"


def load_input(
    session: Session, reading: Reading, spread: TarotSpread, positions: list[tuple[SpreadPosition, ReadingCard]],
) -> InterpretationInput:
    category = session.get(Category, reading.category_id)
    if category is None or category.slug not in CATEGORY_MEANING_FIELDS:
        raise ValueError("Unknown interpretation category")
    category_field = CATEGORY_MEANING_FIELDS[category.slug]
    question = reading.custom_question
    if reading.question_id is not None:
        preset = session.get(Question, reading.question_id)
        question = preset.prompt_th if preset is not None and preset.category_id == reading.category_id else None
    cards = session.scalars(
        select(TarotCard).options(joinedload(TarotCard.meaning))
        .where(TarotCard.id.in_([item.card_id for _, item in positions]))
    )
    cards_by_id = {card.id: card for card in cards}
    fixed_cards = []
    for position, item in positions:
        card = cards_by_id[item.card_id]
        meaning = card.meaning
        keywords = getattr(meaning, f"{item.orientation}_keywords", None)
        keywords = keywords[:8] if isinstance(keywords, list) else []
        fixed_cards.append(FixedCard(
            position=position.position_number, position_name=position.meaning_th,
            position_meaning=position.meaning_th,
            card_id=item.card_id, name_en=card.name_en, name_th=card.name_th,
            orientation=item.orientation,
            keywords=[
                excerpt for word in keywords[:8]
                if isinstance(word, str) and (excerpt := _excerpt(word, 100))
            ],
            orientation_meaning=_excerpt(getattr(meaning, f"{item.orientation}_description", None), 900) or None,
            category_meaning=_excerpt(getattr(meaning, category_field, None), 900) or None,
        ))
    return InterpretationInput(
        reading_id=reading.id, category=category.slug, category_name=category.name_th, question=question,
        spread=spread.name_th, card_count=spread.card_count, cards=fixed_cards,
    )


def cached_result(
    session: Session, reading_id: str, positions: list[tuple[SpreadPosition, ReadingCard]],
) -> InterpretationResult | None:
    row = session.scalar(select(ReadingInterpretation).where(ReadingInterpretation.reading_id == reading_id))
    if row is None:
        return None
    result = InterpretationResult.model_validate(row.result)
    result.check_cards(reading_id, [
        CardIdentity(position=position.position_number, position_name=position.meaning_th,
                     card_id=card.card_id, orientation=card.orientation)
        for position, card in positions
    ])
    return result


def _answer_question(payload: InterpretationInput) -> tuple[str, list[str]]:
    question = "".join(payload.question.split())
    timing = any(cue in question for cue in TIMING_CUES)
    if payload.category == "career":
        looking_for_work = any(cue in question for cue in JOB_SEARCH_CUES)
        if timing and any(cue in question for cue in JOB_OFFER_CUES):
            return (
                "ไพ่บอกวันได้งานใหม่แน่นอนไม่ได้ ให้ดูความคืบหน้าจากสัญญาณจริง เช่น เจอประกาศงานที่ตรงกับคุณ "
                "มีบริษัทติดต่อกลับ หรือได้รับนัดสัมภาษณ์",
                ["เลือกประกาศงานที่อยากสมัครหนึ่งตำแหน่ง แล้วปรับเรซูเม่ให้เห็นผลงานที่ตรงกับหน้าที่ในประกาศ"],
            )
        if timing and "เปลี่ยนงาน" in question:
            return (
                "ถ้ากำลังเลือกจังหวะย้ายงาน ให้ดูว่าได้รับข้อเสนอที่มีเงื่อนไขชัดเจนและจัดการงานเดิมได้เมื่อไหร่",
                ["เช็กวันเริ่มงานที่บริษัทใหม่เสนอและระยะเวลาแจ้งลาออกของงานปัจจุบัน ก่อนตกลงวันย้าย"],
            )
        if timing and looking_for_work:
            return (
                "ถ้าเจอประกาศที่ตรงกับทักษะและมีตัวอย่างผลงานพร้อม ก็เริ่มสมัครได้เลย ให้ยึดกำหนดปิดรับสมัครเป็นหลัก",
                ["เลือกประกาศงานหนึ่งตำแหน่ง แล้วเช็กวันปิดรับสมัครกับเอกสารที่ต้องส่ง"],
            )
        for cue, summary, action in CAREER_QUESTION_GUIDANCE:
            if cue in question:
                return summary, [action]
        if looking_for_work:
            return (
                "ถ้ากำลังเตรียมหางาน ลองดูว่างานแบบไหนที่เหมาะกับคุณ และมีผลงานชิ้นไหนที่แสดงให้เห็นว่าคุณทำได้",
                ["เลือกประกาศงานที่สนใจหนึ่งตำแหน่ง แล้วจับคู่คุณสมบัติที่เขาต้องการกับตัวอย่างผลงานของคุณ"],
            )
    if payload.category == "love" and any(who in question for who in ("เขา", "เค้า", "อีกฝ่าย", "คนคุย")) and any(
        cue in question for cue in ("คิดอย่างไร", "คิดยังไง", "รู้สึกอย่างไร", "รู้สึกยังไง", "คิดอะไร")
    ):
        return (
            "ไพ่บอกแทนเขาไม่ได้ว่าเขาคิดหรือรู้สึกยังไง ลองดูว่าที่เขาพูดและทำสอดคล้องกันแค่ไหน",
            ["ถ้าอยากคุยให้ชัด ลองถามว่า ‘ช่วงนี้เธอมองความสัมพันธ์ของเรายังไงบ้าง’ แล้วให้เวลาเขาตอบ"],
        )
    summary = CATEGORY_SUMMARIES[payload.category]
    if timing:
        summary = f"ไพ่ระบุวันหรือช่วงเวลาที่แน่นอนไม่ได้ {summary}"
    return summary, [CATEGORY_ACTIONS[payload.category]]


def _card_observation(card: FixedCard) -> str | None:
    if card.orientation_meaning:
        return _excerpt(card.orientation_meaning, 150)
    if card.keywords:
        return f"คำสำคัญของไพ่{card.name_th}คือ ‘{card.keywords[0]}’"
    return None


def _card_topic(card: FixedCard) -> str | None:
    return next((PLAIN_TOPICS[keyword] for keyword in card.keywords if keyword in PLAIN_TOPICS), None)


def _card_summary(payload: InterpretationInput) -> str | None:
    # The short answer adds one takeaway. The longer synthesis covers the other positions.
    card = payload.cards[1] if payload.card_count == 3 else payload.cards[-1]
    role = {3: "อุปสรรค", 5: "คำแนะนำ", 10: "ทิศทางที่เป็นไปได้"}[payload.card_count]
    topic = _card_topic(card)
    if topic:
        return f"ไพ่{card.name_th}ในตำแหน่ง{role}ชวนให้ดูว่า{topic}มีผลกับเรื่องนี้ไหม"
    observation = _card_observation(card)
    if observation:
        return f"ลองดูมุม{role}จากไพ่{card.name_th}ประกอบ {observation}"
    return None


def _card_action(payload: InterpretationInput) -> str | None:
    # Choose the actionable role, rather than reusing the card highlighted in the short answer.
    card = payload.cards[{3: 2, 5: 3, 10: 6}[payload.card_count]]
    if (payload.category == "career" and card.orientation == "upright" and "แลกเปลี่ยน" in card.keywords
            and any(cue in payload.question for cue in JOB_SEARCH_CUES)):
        return f"ตามแนวของไพ่{card.name_th} ลองให้คนที่รู้จักสายงานอ่านเรซูเม่ แล้วถามว่าผลงานข้อไหนตรงกับประกาศที่สุด"
    if card.orientation == "upright" and card.category_meaning:
        return f"ถ้าเข้ากับสถานการณ์ของคุณ {_excerpt(card.category_meaning, 180)} ตามแนวของไพ่{card.name_th}"
    topic = _card_topic(card)
    if topic:
        return f"ลองนึกถึงเหตุการณ์จริงที่เกี่ยวกับ{topic} แล้วดูว่ามีส่วนไหนที่คุณปรับได้หนึ่งอย่าง"
    observation = _card_observation(card)
    if observation:
        return f"จดเหตุการณ์ที่เกี่ยวกับคำถามหนึ่งครั้ง แล้วดูว่าตรงกับข้อสังเกตจากไพ่{card.name_th}ไหม — {observation}"
    return None


def _synthesis_question(payload: InterpretationInput) -> str:
    question = "".join(payload.question.split())
    if payload.category == "career":
        if any(cue in question for cue in TIMING_CUES) and any(cue in question for cue in JOB_OFFER_CUES):
            return "การหางานใหม่"
        if "เปลี่ยนงาน" in question:
            return "การย้ายงาน"
        if "เติบโต" in question:
            return "การเติบโตในงาน"
        if "เพื่อนร่วมงาน" in question:
            return "การทำงานกับคนอื่น"
        if any(cue in question for cue in JOB_SEARCH_CUES):
            return "การสมัครงาน"
    return SYNTHESIS_QUESTIONS[payload.category]


def _synthesis_topic(*cards: FixedCard, default: str) -> str:
    # Use orientation-specific keywords. For a group of positions, a shared idea
    # takes precedence over a single observation, keeping long spreads readable.
    topics = [
        next((SYNTHESIS_TOPICS[word] for word in card.keywords if word in SYNTHESIS_TOPICS),
             next((word for word in card.keywords if len(word) <= 32), None))
        for card in cards
    ]
    matches = Counter(topic for topic in topics if topic)
    return matches.most_common(1)[0][0] if matches else default


def _connect_cards(payload: InterpretationInput) -> str:
    focus = _synthesis_question(payload)
    if payload.card_count == 3:
        situation, obstacle, advice = payload.cards
        current = _synthesis_topic(situation, default="สิ่งที่กำลังเกิดขึ้น")
        friction = _synthesis_topic(obstacle, default="จุดที่ยังติดขัด")
        opening = _synthesis_topic(advice, default="ทางเลือกที่พอทำได้")
        return (
            f"สำหรับ{focus} ไพ่ทั้งสามใบสะท้อนว่า{current}กำลังเจอกับ{friction} "
            f"ทางที่ไพ่แนะนำคือ{opening} ลองดูว่ามันช่วยให้เรื่องที่ติดอยู่ขยับได้จริงแค่ไหน"
        )
    if payload.card_count == 5:
        situation, root, obstacle, resource, advice = payload.cards
        current = _synthesis_topic(situation, default="เรื่องที่รับมืออยู่")
        cause = _synthesis_topic(root, default="เงื่อนไขเดิม")
        friction = _synthesis_topic(obstacle, default="สิ่งที่ทำให้ยังตัดสินใจไม่ได้")
        support = _synthesis_topic(resource, default="สิ่งที่คุณพอใช้เป็นแรงช่วยได้")
        opening = _synthesis_topic(advice, default="ทางเลือกที่พอทำได้")
        return (
            f"สำหรับ{focus} ไพ่ชี้ว่า{current}ไม่ได้เกิดขึ้นลอย ๆ แต่มี{cause}อยู่เบื้องหลัง "
            f"เมื่อเจอ{friction}จึงยิ่งไปต่อยากขึ้น {support}อาจช่วยให้คุณพิจารณา{opening}ได้ชัดกว่าเดิม"
        )
    situation, crossing, goal, root, past, near_future, self_view, environment, hopes, direction = payload.cards
    pressure = _synthesis_topic(crossing, situation, root, past, default="เงื่อนไขที่ยังติดอยู่")
    priority = _synthesis_topic(goal, hopes, default="สิ่งที่อยากให้เปลี่ยน")
    support = _synthesis_topic(environment, self_view, default="สิ่งที่คุณปรับหรือขอความช่วยเหลือได้")
    opening = _synthesis_topic(direction, near_future, default="ทางที่ลองเดินต่อได้")
    return (
        f"สำหรับ{focus} ไพ่หลายตำแหน่งสะท้อนว่า{pressure}กำลังชนกับ{priority} "
        f"ถ้าอยากขยับจากจุดนี้ ลองดูว่า{support}ช่วยลดแรงกดนั้นได้ไหม "
        f"และ{opening}ยังเป็นทางที่เหมาะกับสถานการณ์จริงหรือเปล่า"
    )


def database_interpretation(payload: InterpretationInput) -> InterpretationResult:
    card_interpretations = []
    for card in payload.cards:
        orientation = "ตั้งตรง" if card.orientation == "upright" else "กลับหัว"
        label = f"ไพ่{card.name_th}{orientation}ในตำแหน่ง{card.position_meaning}"
        if card.orientation_meaning:
            parts = [label, card.orientation_meaning]
        elif card.keywords:
            parts = [label, f"คำสำคัญของใบนี้คือ ‘{card.keywords[0]}’"]
        else:
            parts = [label, "มีข้อมูลความหมายของทิศนี้ไม่พอ จึงควรดูประกอบกับสิ่งที่เกิดขึ้นจริง"]
        if card.category_meaning and card.category_meaning != card.orientation_meaning:
            parts.append(f"ถ้าโยงกับคำถามของคุณ {card.category_meaning}")
        card_interpretations.append(CardInterpretation(
            position=card.position, position_name=card.position_name,
            card_id=card.card_id, orientation=card.orientation,
            interpretation=" ".join(parts),
        ))

    summary, guidance = _answer_question(payload)
    if takeaway := _card_summary(payload):
        summary = f"{summary} {takeaway}"
    if action := _card_action(payload):
        guidance.append(action)
    return InterpretationResult(
        reading_id=payload.reading_id, language="th",
        overall_summary=summary,
        card_interpretations=card_interpretations,
        card_connections=_connect_cards(payload),
        practical_guidance=guidance,
        closing_message="เก็บส่วนที่ตรงกับชีวิตจริงไว้ใช้ และวางส่วนที่ไม่ตรงไว้ก่อน",
    )


def save_result(session: Session, reading: Reading, result: InterpretationResult, model: str | None) -> None:
    session.add(ReadingInterpretation(
        reading_id=reading.id, result=result.model_dump(mode="json"),
        source="ai" if model is not None else "database", model=model,
    ))
    reading.status = "COMPLETED"


def _reserve_attempt(
    session: Session, reading_id: str, provider: Provider, settings: Settings, quota_scope: str,
) -> int | None:
    with session.begin():
        start_write(session)
        # The first seeded category is a shared mutex for budget reservations.
        # Acquire it before the first consistent read on MySQL's REPEATABLE READ.
        session.scalar(select(Category.id).order_by(Category.id).limit(1).with_for_update())
        status = session.scalar(select(Reading.status).where(Reading.id == reading_id).with_for_update())
        now = utc_now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today = select(func.count(AIUsageLog.id)).where(
            AIUsageLog.created_at >= midnight, AIUsageLog.created_at < midnight + timedelta(days=1),
        )
        scope_limit = (
            settings.ai_account_daily_request_limit if quota_scope.startswith("user:")
            else settings.ai_guest_ip_daily_request_limit
        )
        if (
            status != "INTERPRETING"
            or session.scalar(today) >= settings.ai_daily_request_limit
            or session.scalar(today.where(AIUsageLog.quota_scope == quota_scope)) >= scope_limit
        ):
            return None
        row = AIUsageLog(
            reading_id=reading_id, provider=provider.name, model=provider.model,
            status="started", created_at=now, quota_scope=quota_scope,
        )
        session.add(row)
        session.flush()
        return row.id


def generate(
    session: Session, reading_id: str, payload: InterpretationInput, provider: Provider, settings: Settings,
    quota_scope: str,
) -> InterpretationResult | None:
    for number in range(ATTEMPTS):
        attempt_id = _reserve_attempt(session, reading_id, provider, settings, quota_scope)
        if attempt_id is None:
            break
        attempt = provider.interpret(payload)
        if attempt.result is not None:
            try:
                attempt.result.check_cards(payload.reading_id, payload.cards)
                attempt.result.check_fresh_prose(payload.cards)
            except ValueError:
                attempt = replace(attempt, result=None, status="invalid_response", retryable=False)
        with session.begin():
            log = session.get(AIUsageLog, attempt_id)
            log.status = attempt.status
            log.input_tokens = attempt.input_tokens
            log.output_tokens = attempt.output_tokens
            log.cost_estimate = provider.estimate_cost(attempt)
        if attempt.result is not None:
            return attempt.result
        if not attempt.retryable or number == ATTEMPTS - 1:
            break
        sleep(0.25)
    return None
