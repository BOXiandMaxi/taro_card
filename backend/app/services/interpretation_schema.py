from collections import Counter
from collections.abc import Sequence
from itertools import combinations
from typing import Annotated, Literal
from unicodedata import category, normalize

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

CategorySlug = Literal["daily-life", "finance", "love", "career", "guidance"]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


def _normalize_prose(prose: str) -> str:
    return "".join(char for char in normalize("NFC", prose).casefold() if category(char)[0] in "LMN")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CardIdentity(StrictModel):
    position: Annotated[int, Field(ge=1, le=10)]
    position_name: Text
    card_id: Annotated[int, Field(ge=1, le=78)]
    orientation: Literal["upright", "reversed"]


class FixedCard(CardIdentity):
    position_meaning: Text
    name_th: Text
    name_en: Text
    keywords: list[Text]
    orientation_meaning: Text | None
    category_meaning: Text | None


class InterpretationInput(StrictModel):
    reading_id: Text
    category: CategorySlug
    category_name: Text
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    spread: Text
    card_count: Literal[3, 5, 10]
    cards: list[FixedCard]

    @model_validator(mode="after")
    def check_fixed_cards(self):
        if [card.position for card in self.cards] != list(range(1, self.card_count + 1)):
            raise ValueError("Cards must cover the spread in position order")
        if len({card.card_id for card in self.cards}) != self.card_count:
            raise ValueError("Card IDs must be distinct")
        return self


class CardInterpretation(CardIdentity):
    interpretation: Text


class InterpretationResult(StrictModel):
    reading_id: Text
    language: Literal["th"]
    overall_summary: Text
    card_interpretations: Annotated[list[CardInterpretation], Field(min_length=3, max_length=10)]
    card_connections: Text
    practical_guidance: Annotated[list[Text], Field(min_length=1, max_length=5)]
    closing_message: Text

    def check_cards(self, reading_id: str, expected: Sequence[CardIdentity]) -> None:
        if self.reading_id != reading_id:
            raise ValueError("Interpretation belongs to a different reading")
        result_keys = [(card.position, card.position_name, card.card_id, card.orientation) for card in self.card_interpretations]
        expected_keys = [(card.position, card.position_name, card.card_id, card.orientation) for card in expected]
        if result_keys != expected_keys:
            raise ValueError("Interpretation must preserve every drawn card, position and orientation")

    def check_fresh_prose(self, expected: Sequence[FixedCard]) -> None:
        card_prose = [card.interpretation for card in self.card_interpretations]
        for prose in (
            self.overall_summary, self.card_connections, self.closing_message,
            *self.practical_guidance, *card_prose,
        ):
            thai = sum("\u0e01" <= char <= "\u0e2e" for char in prose)
            other = sum(char.isalpha() and not "\u0e00" <= char <= "\u0e7f" for char in prose)
            # Allow names and quoted foreign terms in otherwise Thai prose.
            if not thai or (other >= 30 and other > 5 * thai):
                raise ValueError("Interpretation prose must be in Thai")

        normalized = [_normalize_prose(prose) for prose in card_prose]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Each card must have distinct interpretation prose")

        trigrams = []
        for prose, card in zip(normalized, expected, strict=True):
            for name in (card.name_th, card.name_en):
                if normalized_name := _normalize_prose(name):
                    prose = prose.replace(normalized_name, "@")
            padded = f"^{prose}$"
            trigrams.append(Counter(padded[index:index + 3] for index in range(len(prose))))

        # Character trigrams keep local Thai wording together without requiring word breaks.
        # Require 90% Dice overlap across whole paragraphs so shared terms or openings can pass.
        for first, second in combinations(trigrams, 2):
            shared = (first & second).total()
            if 2 * shared / (first.total() + second.total()) >= 0.90:
                raise ValueError("Each card must have distinct interpretation prose")

        summary = _normalize_prose(self.overall_summary)
        connections = _normalize_prose(self.card_connections)
        if summary == connections:
            raise ValueError("Card connections must add to the overall summary")
        summary_trigrams = Counter(f"^{summary}$"[index:index + 3] for index in range(len(summary)))
        connection_trigrams = Counter(f"^{connections}$"[index:index + 3] for index in range(len(connections)))
        shared = (summary_trigrams & connection_trigrams).total()
        if 2 * shared / (summary_trigrams.total() + connection_trigrams.total()) >= 0.90:
            raise ValueError("Card connections must add to the overall summary")
