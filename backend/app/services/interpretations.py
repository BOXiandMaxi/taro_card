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
# Match stored labels so a different layout cannot inherit a role by position number alone.
POSITION_ROLE_DESCRIPTIONS = {
    "สถานการณ์ปัจจุบัน": "อธิบายสภาพของเรื่องที่ถามในตอนนี้ เพื่อเป็นจุดตั้งต้นของคำอ่าน",
    "อุปสรรคหรืออิทธิพลหลัก": "ชี้แรงกดดันหรือปัจจัยหลักที่ทำให้สถานการณ์เดินหน้าได้ยากหรือเปลี่ยนทิศ",
    "คำแนะนำ": "บอกสิ่งที่ผู้ถามลองทำหรือสังเกตต่อได้ เพื่อตอบสนองต่อสถานการณ์และอุปสรรค",
    "สาเหตุที่เป็นรากฐาน": "ชี้เงื่อนไขหรือรูปแบบที่อาจอยู่เบื้องหลังสถานการณ์ปัจจุบัน",
    "อุปสรรคหลัก": "ระบุปัญหาเฉพาะที่ขัดขวางความคืบหน้า และดูว่ารากฐานทำให้อุปสรรคคงอยู่หรือไม่",
    "จุดแข็งและทรัพยากรที่มี": "มองหาทักษะ คนช่วย หรือทรัพยากรที่อาจใช้รับมืออุปสรรค",
    "คำแนะนำและแนวทางที่เป็นไปได้": "เสนอขั้นตอนที่ใช้จุดแข็งหรือทรัพยากรเพื่อรับมืออุปสรรค",
    "อิทธิพลที่เข้ามาขวาง": "แสดงแรงที่เข้ามาปะทะกับสถานการณ์ปัจจุบันและทำให้โจทย์ซับซ้อนขึ้น",
    "เป้าหมายที่ตระหนักรู้": "สำรวจสิ่งที่ผู้ถามอาจกำลังมุ่งหวังอย่างรู้ตัวในเรื่องนี้",
    "รากฐานของสถานการณ์": "พิจารณาเงื่อนไขที่หล่อเลี้ยงสถานการณ์อยู่เบื้องหลัง แยกจากเป้าหมายที่ผู้ถามเล็งไว้",
    "อดีตที่ผ่านมาไม่นาน": "มองเหตุการณ์หรือพฤติกรรมก่อนหน้าในช่วงใกล้ ๆ ที่อาจยังมีผลกับเรื่องปัจจุบัน",
    "อนาคตอันใกล้": "อ่านพัฒนาการระยะถัดไปที่อาจเห็นหากเงื่อนไขปัจจุบันยังดำเนินต่อ",
    "มุมมองต่อตนเอง": "สำรวจท่าทีที่ผู้ถามอาจมีต่อตนเองและผลของท่าทีนั้นต่อทางเลือก",
    "สภาพแวดล้อมรอบตัว": "พิจารณาปัจจัยภายนอก รวมถึงเงื่อนไขหรือการสนับสนุนที่อาจมีผลต่อทางเลือก",
    "ความหวังและความกลัว": "มองความคาดหวังหรือความกังวลที่อาจทำให้ผู้ถามให้น้ำหนักกับบางทางเลือก",
    "ทิศทางที่เป็นไปได้": "ประมวลทิศทางจากทั้งผังและบอกเงื่อนไขที่อาจทำให้ทิศทางเปลี่ยนได้",
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
# Prefer a direct answer for common questions, including free-text variants.
# Each entry gives the conclusion, what to try, and what to check afterward.
QUESTION_ANSWERS = {
    "daily-life": (
        (("ใส่ใจ", "ให้ความสำคัญ"), "วันนี้ให้เริ่มจากเรื่องที่ปล่อยไว้แล้วจะทำให้เรื่องอื่นติดตามไปด้วย",
         "เขียนสิ่งที่ต้องทำวันนี้ แล้วเลือกหนึ่งอย่างที่คนอื่นกำลังรอหรือมีเส้นตายชัด",
         "พอทำขั้นแรกเสร็จ ดูว่างานที่เหลือเริ่มเดินต่อได้ไหม ถ้ายังติด ให้ถามคนที่ช่วยปลดจุดนั้นได้"),
        (("ระวัง", "อุปสรรค"), "จุดที่ควรระวังคือเรื่องที่เกิดซ้ำและทำให้แผนสะดุด",
         "เลือกเหตุการณ์ล่าสุดที่ทำให้แผนหลุด แล้วแยกว่าติดเวลา ข้อมูล หรือข้อตกลง",
         "ลองเปลี่ยนเงื่อนไขทีละอย่าง แล้วดูว่าปัญหาเดิมเกิดน้อยลงไหม"),
        (("เปลี่ยนแปลง",), "เริ่มเปลี่ยนจากสิ่งที่ทำซ้ำแล้วได้ผลไม่เหมือนที่ต้องการ เพราะเห็นผลของวิธีใหม่ได้ง่ายกว่า",
         "เลือกกิจวัตรหนึ่งอย่างแล้วลองเปลี่ยนเฉพาะเวลา คนที่ช่วย หรือวิธีทำ",
         "ผ่านไปสองหรือสามครั้ง ให้ดูว่าวิธีใหม่ช่วยลดเวลา ความเหนื่อย หรือเรื่องที่ต้องกลับมาแก้ไหม"),
    ),
    "finance": (
        (("ลงทุน", "เสี่ยง"), "สิ่งสำคัญก่อนตัดสินใจคือรู้ให้ชัดว่าถ้าเรื่องไม่เป็นตามคาด คุณจะรับผลเสียได้แค่ไหน",
         "จดค่าใช้จ่าย เงื่อนไขที่ผูกมัด และข้อมูลที่ยังไม่ได้ยืนยันจากแหล่งที่เชื่อถือได้",
         "ถ้ายังอธิบายต้นทุนหรือผลในกรณีแย่ที่สุดไม่ได้ ให้หาข้อมูลหรือถามผู้เชี่ยวชาญก่อนตัดสินใจ"),
        (("รายได้",), "ให้มองหาแหล่งรายได้ที่ทดลองเล็ก ๆ ได้และมีคนสนใจจริงก่อนทุ่มเวลาเพิ่ม",
         "เลือกทางเลือกหนึ่งแล้วจดว่าต้องใช้เวลาและต้นทุนเท่าไร เทียบกับสิ่งที่คนยอมจ่ายจริง",
         "ดูว่ามีคนสอบถามหรือซื้อซ้ำหลังทดลองไหม ใช้ข้อมูลนี้เทียบกับแรงที่ต้องลง"),
        (("วางแผน", "อุปสรรค", "สถานการณ์"), "ให้ดูว่าเงินตึงเพราะรายจ่ายต่อเนื่องหรือเพราะวันรับเงินกับวันจ่ายไม่ตรงกัน สองอย่างนี้ต้องจัดการต่างกัน",
         "เปิดข้อมูลเดือนล่าสุดแล้วแยกเงินเข้าจริง ค่าใช้จ่ายประจำ และค่าใช้จ่ายที่เกิดครั้งเดียว",
         "ถ้ายอดรวมยังพอแต่เงินขาดช่วง ให้ลองทำปฏิทินวันรับและวันจ่าย ถ้ายอดรวมไม่พอ ค่อยดูว่ารายจ่ายส่วนไหนเปลี่ยนได้"),
    ),
    "love": (
        (("คนโสด", "รักครั้งใหม่"), "ลองเปิดโอกาสให้คนใหม่ ๆ โดยดูว่าคุยแล้วสบายใจและต่างฝ่ายต่างเข้าหากันไหม",
         "ถ้าอยากรู้จักใครเพิ่ม ชวนคุยเรื่องที่สนใจร่วมกันหรือนัดทำกิจกรรมสั้น ๆ",
         "สังเกตว่าอีกฝ่ายริเริ่มคุยบ้างและเคารพเวลาหรือขอบเขตของคุณไหม"),
        (("ปรับปรุง", "สื่อสาร", "คุย", "ความสัมพันธ์ปัจจุบัน"), "ถ้าอยากรู้ว่าความสัมพันธ์จะดีขึ้นได้ไหม เริ่มจากคุยเรื่องที่เกิดขึ้นจริงหนึ่งเรื่องและดูว่าทั้งคู่พร้อมขยับหรือเปล่า",
         "เลือกเหตุการณ์หนึ่ง แล้วลองพูดว่า ‘ตอนเกิดเรื่องนี้เรารู้สึกแบบนี้ คราวหน้าเราลองตกลงกันใหม่ได้ไหม’",
         "ฟังว่าอีกฝ่ายเข้าใจสิ่งที่คุณต้องการอย่างไร แล้วดูว่าข้อตกลงถูกนำไปทำจริงไหม"),
        (("อดีต",), "บทเรียนที่ใช้ได้คือรู้ว่าความสัมพันธ์แบบไหนทำให้คุณเป็นตัวเองได้และขอบเขตไหนที่อยากรักษา",
         "จดหนึ่งเหตุการณ์ที่รู้สึกว่าได้รับการเคารพ และอีกหนึ่งเหตุการณ์ที่ฝืนใจ",
         "แปลงข้อสังเกตเป็นขอบเขตที่บอกอีกฝ่ายได้ แล้วดูจากการตอบรับจริง"),
    ),
    "career": (
        (("อุปสรรค", "ติดขัด"), "ให้หาว่างานหยุดที่ขั้นตอนไหนก่อนแก้ เพราะเรื่องเวลา ข้อมูล และอำนาจตัดสินใจต้องแก้คนละแบบ",
         "ไล่จากงานล่าสุดที่ค้างว่าใครต้องตอบหรือส่งอะไรเพื่อให้ไปต่อได้",
         "เมื่อได้ข้อมูลหรือข้อตกลงแล้ว ดูว่างานเริ่มเดินหรือยังติดที่ขั้นอื่น"),
    ),
    "guidance": (
        (("ปล่อยวาง",), "ลองวางความรับผิดชอบส่วนที่คุณไม่มีอำนาจกำหนดผล แล้วเก็บแรงไว้ทำส่วนที่คุณเลือกได้",
         "จดสิ่งที่ค้างใจหนึ่งเรื่อง แล้วแยกว่าอะไรเป็นการตัดสินใจของคุณและอะไรขึ้นกับคนอื่น",
         "กำหนดว่าคุณจะกลับมาคิดเรื่องนี้อีกเมื่อมีข้อมูลใหม่อะไร จะได้ไม่ต้องทบทวนเรื่องเดิมตลอดเวลา"),
        (("จุดแข็ง",), "จุดแข็งที่น่าดูคือสิ่งที่คุณทำได้ดีหลายครั้ง แม้จะรู้สึกว่าเป็นเรื่องธรรมดา",
         "นึกถึงครั้งที่คนอื่นขอให้คุณช่วย แล้วจดว่าคุณทำอะไรให้เรื่องง่ายขึ้น",
         "ลองนำวิธีเดียวกันไปใช้กับเรื่องที่กำลังติด แล้วเทียบว่าผลดีขึ้นตรงไหน"),
        (("มองข้าม", "บทเรียน"), "สิ่งที่น่าทบทวนคือเงื่อนไขที่ทำให้คุณเจอปัญหาเดิมแม้สถานการณ์จะเปลี่ยนไปแล้ว",
         "เทียบเหตุการณ์สองครั้งที่ลงเอยคล้ายกัน แล้วหาว่าคุณรับปาก รอคำตอบ หรือตัดสินใจในจังหวะเดียวกันไหม",
         "เลือกเปลี่ยนเพียงจุดเดียวในครั้งถัดไป แล้วดูว่าผลลัพธ์ต่างจากเดิมไหม"),
    ),
}
CATEGORY_CHECKS = {
    "daily-life": "หลังลองทำหนึ่งอย่าง ให้ดูว่าเวลาที่ใช้หรือเรื่องที่ค้างลดลงจริงไหม",
    "finance": "ก่อนตัดสินใจ ให้เทียบตัวเลขจากหลักฐานที่มีจริงกับยอดที่คุณคาดไว้ แล้วหาที่มาของส่วนต่าง",
    "love": "หลังพูดคุย ให้ดูว่าต่างฝ่ายเข้าใจตรงกันและทำตามที่คุยกันได้แค่ไหน",
    "career": "รอบถัดไปให้วัดจากสิ่งที่เปลี่ยนจริง เช่น งานค้างลดลง ได้คำตอบ หรือนัดคุยเกิดขึ้น",
    "guidance": "ลองวิธีนี้กับสถานการณ์หนึ่งครั้ง แล้วดูว่าอะไรเปลี่ยนก่อนตัดสินใจว่าจะใช้ต่อไหม",
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
            position_meaning=POSITION_ROLE_DESCRIPTIONS.get(position.meaning_th, position.meaning_th),
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
                ["เลือกประกาศงานที่อยากสมัครหนึ่งตำแหน่ง แล้วปรับเรซูเม่ให้เห็นผลงานที่ตรงกับหน้าที่ในประกาศ",
                 "จดวันส่งใบสมัครและผลตอบกลับ ถ้าส่งหลายตำแหน่งแล้วยังไม่ถูกเรียก ให้เทียบหน้าที่ในประกาศกับผลงานที่ใส่ไว้ แล้วปรับส่วนที่ยังไม่ตรง"],
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
            ["ถ้าอยากคุยให้ชัด ลองถามว่า ‘ช่วงนี้เธอมองความสัมพันธ์ของเรายังไงบ้าง’ แล้วให้เวลาเขาตอบ",
             "ดูว่าอีกฝ่ายให้เวลา รักษาคำพูด และริเริ่มติดต่ออย่างสม่ำเสมอไหม เทียบกับสิ่งที่เขาบอกในบทสนทนา"],
        )
    for cues, summary, action, check in QUESTION_ANSWERS[payload.category]:
        if any(cue in question for cue in cues):
            if timing:
                summary = f"ไพ่ระบุวันหรือช่วงเวลาที่แน่นอนไม่ได้ {summary}"
            return summary, [action, check]
    summary = CATEGORY_SUMMARIES[payload.category]
    if timing:
        summary = f"ไพ่ระบุวันหรือช่วงเวลาที่แน่นอนไม่ได้ {summary}"
    return summary, [CATEGORY_ACTIONS[payload.category]]


def _focus(payload: InterpretationInput) -> str:
    question = "".join(payload.question.split())
    if payload.category == "career":
        if any(cue in question for cue in JOB_OFFER_CUES):
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


def _summary_reference(payload: InterpretationInput) -> str | None:
    obstacle = payload.cards[2 if payload.card_count == 5 else 1]
    meaning = obstacle.orientation_meaning
    if not meaning or len(meaning) > 220:
        return None
    return (
        f"ถ้าจะใช้ไพ่ช่วยทบทวน ให้เริ่มจากไพ่{obstacle.name_th}ในตำแหน่งอุปสรรค "
        f"ความหมายที่บันทึกไว้คือ «{meaning}» ใช้เป็นข้อสังเกตเพื่อเทียบกับเหตุการณ์จริง"
    )


def _card_action(payload: InterpretationInput) -> str | None:
    card = payload.cards[{3: 2, 5: 3, 10: 7}[payload.card_count]]
    question = "".join(payload.question.split())
    if payload.category == "career" and any(cue in question for cue in (*JOB_SEARCH_CUES, *JOB_OFFER_CUES)):
        if "แลกเปลี่ยน" in card.keywords:
            return "ส่งประกาศกับเรซูเม่ให้คนที่รู้จักสายงานช่วยอ่าน แล้วถามว่าผลงานข้อไหนทำให้เห็นชัดว่าคุณทำงานนี้ได้"
        if "เข้าใจคลาด" in card.keywords:
            return "ถ้าหน้าที่ในประกาศตีความได้หลายแบบ ให้ถามผู้ติดต่อว่าในสามเดือนแรกวัดผลงานจากอะไร แล้วเช็กว่าตรงกับงานที่คุณหาอยู่ไหม"
    return None


def _spread_guide(payload: InterpretationInput) -> str:
    focus = _focus(payload)
    if payload.card_count == 3:
        return (
            f"เวลาอ่านไพ่ชุดนี้ประกอบ{focus} ให้เทียบสองใบแรกกับเหตุการณ์จริงก่อน "
            "ใบแรกใช้ดูว่าเกิดอะไรขึ้น ส่วนใบที่สองใช้ถามว่าอะไรทำให้เรื่องไปต่อได้ยาก "
            "ถ้าเห็นจุดที่ติดแล้ว ค่อยดูว่าคำแนะนำในใบสุดท้ายช่วยคลายจุดนั้นได้จริงไหม"
        )
    if payload.card_count == 5:
        return (
            f"เวลาใช้ไพ่ชุดนี้ทบทวน{focus} ให้แยกสิ่งที่เห็นตอนนี้ออกจากสาเหตุเดิมและเรื่องที่กำลังขวาง "
            "ถ้าสิ่งที่ขวางเกิดขึ้นซ้ำ ให้ดูว่าการแก้แค่ปัญหาเฉพาะหน้าจะช่วยได้แค่ไหน\n\n"
            "สองใบสุดท้ายช่วยให้คิดถึงตัวช่วยที่มีและทางเลือกที่ใช้ได้จริง "
            "ให้พิจารณาว่าทางเลือกนั้นแตะสาเหตุเดิมได้ไหม และคุณมีเวลา แรง หรือคนช่วยพอจะทำต่อหรือเปล่า"
        )
    return (
        f"สำหรับ{focus} ให้เริ่มจากสถานการณ์และอุปสรรค แล้วใช้ไพ่รากฐานกับเหตุการณ์ก่อนหน้าช่วยตั้งคำถามว่า"
        "มีเรื่องอะไรที่เกิดซ้ำ จากนั้นเทียบกับเป้าหมายเพื่อดูว่าสิ่งที่อยากให้เกิดสอดคล้องกับสภาพตอนนี้แค่ไหน\n\n"
        "จากนั้นให้แยกสิ่งที่คุณปรับเองได้ออกจากเงื่อนไขรอบตัว "
        "ความหวังและความกลัวช่วยบอกได้ว่าคุณให้ความสำคัญกับอะไร "
        "ส่วนไพ่ระยะใกล้และไพ่ทิศทางใช้ดูว่าเงื่อนไขอะไรต้องเปลี่ยนก่อนจึงจะเห็นความคืบหน้า "
        "ให้เทียบกับสัญญาณที่เกิดขึ้นจริงก่อนตัดสินใจ"
    )


def database_interpretation(payload: InterpretationInput) -> InterpretationResult:
    card_interpretations = []
    for card in payload.cards:
        orientation = "ตั้งตรง" if card.orientation == "upright" else "กลับหัว"
        label = f"ไพ่{card.name_th}{orientation}ในตำแหน่ง{card.position_name}"
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

    summary, steps = _answer_question(payload)
    first_step, *remaining_steps = steps
    guidance = [first_step]
    if action := _card_action(payload):
        guidance.append(action)
    guidance.extend(remaining_steps or [CATEGORY_CHECKS[payload.category]])
    if reference := _summary_reference(payload):
        summary = f"{summary}\n\n{reference}"
    return InterpretationResult(
        reading_id=payload.reading_id, language="th",
        overall_summary=summary,
        card_interpretations=card_interpretations,
        card_connections=_spread_guide(payload),
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
