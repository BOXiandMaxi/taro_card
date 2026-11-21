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
CAREER_QUESTION_ACTIONS = (
    ("เปลี่ยนงาน", "เทียบงานปัจจุบันกับงานที่สนใจโดยใช้เงื่อนไขเดียวกัน เช่น หน้าที่ เวลา และรายได้ แล้วตรวจข้อมูลที่ยังไม่ชัด"),
    ("เติบโต", "เลือกทักษะที่อยากพัฒนาหนึ่งอย่าง แล้วถามว่ามีงานชิ้นไหนให้ลองฝึกและรับข้อเสนอแนะได้"),
    ("เพื่อนร่วมงาน", "ทบทวนบทสนทนาล่าสุด แล้วเลือกความคาดหวังเรื่องงานหนึ่งข้อที่ควรคุยให้ชัด"),
    ("งานใหม่", "เลือกหน้าที่หนึ่งข้อจากงานใหม่ แล้วจดสิ่งที่ทำได้แล้วและสิ่งที่ต้องฝึกเพิ่ม"),
)
POSITION_REFLECTIONS = {
    3: (
        "ประเด็นนี้ปรากฏอยู่ตรงไหนในสถานการณ์ตอนนี้",
        "ประเด็นนี้อาจทำให้ติดขัดหรือมีอิทธิพลต่อทางเลือกอย่างไร",
        "มีวิธีไหนที่นำประเด็นนี้ไปลองทำได้ในสถานการณ์ของคุณ",
    ),
    5: (
        "ประเด็นนี้คล้ายกับสิ่งที่เกิดขึ้นตอนนี้ตรงไหน",
        "ประเด็นนี้เกี่ยวข้องกับเหตุที่ทำให้สถานการณ์เป็นแบบนี้อย่างไร",
        "ประเด็นนี้อาจบอกอะไรเกี่ยวกับอุปสรรคที่ยังต้องจัดการ",
        "มีทักษะหรือความช่วยเหลืออะไรที่ใช้รับมือกับประเด็นนี้ได้",
        "ทางเลือกไหนที่ลองได้โดยเริ่มจากสิ่งที่มีอยู่",
    ),
    10: (
        "ประเด็นนี้คล้ายกับสิ่งที่กำลังเกิดขึ้นตรงไหน",
        "แรงต้านในประเด็นนี้อาจเปลี่ยนทางเลือกของคุณอย่างไร",
        "ประเด็นนี้ช่วยให้เห็นว่าคุณอยากไปถึงอะไรชัดขึ้นไหม",
        "มีเงื่อนไขหรือความต้องการอะไรอยู่เบื้องหลังประเด็นนี้",
        "เหตุการณ์ที่เพิ่งผ่านไปเกี่ยวข้องกับประเด็นนี้อย่างไร",
        "ถ้าสถานการณ์ยังดำเนินแบบเดิม มีสัญญาณอะไรที่ควรสังเกตในระยะใกล้",
        "วิธีที่คุณมองบทบาทของตัวเองมีผลกับประเด็นนี้อย่างไร",
        "เงื่อนไขรอบตัวข้อไหนที่สังเกตหรือสอบถามให้ชัดได้",
        "ความหวังหรือความกังวลอาจทำให้คุณให้น้ำหนักข้อมูลข้อนี้มากขึ้นไหม",
        "ทิศทางที่เห็นขึ้นอยู่กับเงื่อนไขอะไร และอะไรอาจทำให้เปลี่ยนได้",
    ),
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


def database_interpretation(payload: InterpretationInput) -> InterpretationResult:
    card_interpretations = []
    themes = []
    question_excerpt = _excerpt(payload.question, 120)
    for index, (card, reflection) in enumerate(zip(payload.cards, POSITION_REFLECTIONS[payload.card_count], strict=True)):
        orientation = "ตั้งตรง" if card.orientation == "upright" else "กลับหัว"
        label = f"ไพ่{card.name_th} ({orientation}) อยู่ในตำแหน่ง{card.position_meaning}."
        if card.orientation_meaning:
            parts = [label, card.orientation_meaning]
        elif card.keywords:
            parts = [label, f"ประเด็นสำคัญของใบนี้คือ{card.keywords[0]}"]
        else:
            parts = [label, "มีข้อมูลความหมายของทิศนี้ไม่พอ จึงควรดูประกอบกับสิ่งที่เกิดขึ้นจริง"]
        if card.category_meaning and card.category_meaning != card.orientation_meaning:
            parts.append(f"ในเรื่อง{payload.category_name} {card.category_meaning}")
        parts.append(f"เมื่อเทียบกับคำถาม «{question_excerpt}» {reflection}" if index == 0 else reflection)
        card_interpretations.append(CardInterpretation(
            position=card.position, position_name=card.position_name,
            card_id=card.card_id, orientation=card.orientation,
            interpretation=" ".join(parts),
        ))
        theme = card.keywords[0] if card.keywords else _excerpt(card.orientation_meaning, 85)
        themes.append(
            f"ไพ่{card.name_th} (ประเด็น{theme})" if theme
            else f"ตำแหน่ง{_excerpt(card.position_name, 100)}"
        )

    if payload.card_count == 3:
        situation, obstacle, advice = themes
        connections = (
            f"{situation} เป็นภาพตั้งต้นของสถานการณ์ ขณะที่ {obstacle} อยู่ตรงจุดที่ขัดขวาง "
            f"จึงอาจทำให้เรื่องเดินต่อยากขึ้น ส่วน {advice} อยู่ในตำแหน่งแนวทาง "
            "การจัดการจุดติดขัดก่อนจะช่วยให้เลือกขั้นต่อไปได้ชัดขึ้น"
        )
        focus = "สิ่งที่ติดขัดตอนนี้อาจช่วยบอกว่าควรปรับอะไรเป็นอันดับแรก"
        next_step = "เลือกสิ่งที่ติดขัดหนึ่งข้อ แล้วลองปรับทีละอย่างเพื่อดูว่าอะไรช่วยได้จริง"
    elif payload.card_count == 5:
        situation, root, obstacle, resource, advice = themes
        connections = (
            f"{situation} แสดงสิ่งที่เห็นในตอนนี้ ส่วนรากฐานจาก {root} อาจช่วยอธิบายว่า "
            f"เหตุใด {obstacle} จึงเป็นอุปสรรค ทรัพยากรจาก {resource} กับแนวทางจาก {advice} "
            "จึงควรถูกพิจารณาคู่กันก่อนเลือกสิ่งที่จะลงมือ"
        )
        focus = "ลองแยกสาเหตุออกจากสิ่งที่เห็นตอนนี้ แล้วเลือกทางที่ใช้ทรัพยากรที่มีอยู่"
        next_step = "เลือกจุดแข็งหรือทรัพยากรที่ใช้ได้หนึ่งอย่าง แล้ววางขั้นทดลองเล็ก ๆ ที่ช่วยแก้อุปสรรคหลัก"
    else:
        situation, crossing, goal, root, past, near_future, self_view, environment, hopes, direction = themes
        connections = (
            f"{situation} วางสถานการณ์ไว้คู่กับอิทธิพลที่เข้ามาขวางจาก {crossing} "
            f"เป้าหมายจาก {goal} กับรากฐานจาก {root} ช่วยแยกสิ่งที่อยากได้ออกจากสิ่งที่ผลักดันอยู่ "
            f"อดีตจาก {past} เป็นบริบทให้กับแนวโน้มระยะใกล้จาก {near_future} "
            f"มุมมองต่อตัวเองผ่าน {self_view} และปัจจัยรอบตัวผ่าน {environment} อาจให้น้ำหนักต่างกัน "
            f"ความหวังหรือความกลัวจาก {hopes} จึงไม่ควรถูกใช้แทนข้อมูลเมื่อมองทิศทางจาก {direction}"
        )
        focus = "แยกสิ่งที่คุณปรับได้จากแรงกดดันรอบตัวก่อนชั่งน้ำหนักทิศทางที่เป็นไปได้"
        next_step = "จดสิ่งที่ขึ้นอยู่กับตัวคุณและสิ่งที่ขึ้นอยู่กับสภาพแวดล้อม แล้วเลือกหนึ่งเรื่องที่คุณลงมือได้"

    action = CATEGORY_ACTIONS[payload.category]
    if payload.category == "career":
        action = next((step for cue, step in CAREER_QUESTION_ACTIONS if cue in payload.question), action)
    return InterpretationResult(
        reading_id=payload.reading_id, language="th",
        overall_summary=f"สำหรับคำถาม «{payload.question}» {focus}",
        card_interpretations=card_interpretations,
        card_connections=connections,
        practical_guidance=[action, next_step],
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
