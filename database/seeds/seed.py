"""Run from project root: python -m database.seeds.seed [--check-only]."""
import argparse
from pathlib import Path
import sys

# Resolve app from this file, independent of the current working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from database.seeds.reference_data import (
    CARDS, CATEGORIES, QUESTIONS, SPREADS, POSITIONS, validate_reference_data,
)
from database.seeds.card_meanings import MEANINGS


def seed_reference_data(session):
    """Insert missing IDs; reject collisions; preserve existing editorial content.

    The caller owns the transaction. Sequential reruns are idempotent; operators
    should run only one seed process at a time (concurrent conflicts roll back).
    """
    from sqlalchemy import func, select
    from app.models import CardMeaning, Category, Question, SpreadPosition, TarotCard, TarotSpread

    validate_reference_data()
    groups = (
        (TarotCard, CARDS, ("slug", "arcana", "suit", "rank")),
        (Category, CATEGORIES, ("slug",)),
        (TarotSpread, SPREADS, ("slug", "card_count")),
        (Question, QUESTIONS, ("category_id", "display_order")),
        (SpreadPosition, POSITIONS, ("spread_id", "position_number")),
    )
    inserted = 0
    for model, rows, identity_fields in groups:
        for row in rows:
            existing = session.get(model, row["id"])
            if existing is None:
                session.add(model(**row))
                inserted += 1
            elif any(getattr(existing, key) != row[key] for key in identity_fields):
                raise ValueError(f"Seed ID collision in {model.__tablename__}: {row['id']}")
            elif model is TarotCard:
                if existing.image_filename is None:
                    existing.image_filename = row["image_filename"]
                elif existing.image_filename != row["image_filename"]:
                    raise ValueError(f"Image filename collision for card {row['id']}")
        session.flush()
    if set(MEANINGS) != set(range(1, 79)):
        raise ValueError("Expected one meaning for each of 78 cards")
    for card_id, row in MEANINGS.items():
        existing = session.scalar(select(CardMeaning).where(CardMeaning.card_id == card_id))
        if existing is None:
            session.add(CardMeaning(**row))
            inserted += 1
    session.flush()
    if session.scalar(select(func.count()).select_from(TarotCard)) != 78:
        raise ValueError("Database must contain exactly 78 cards")
    for arcana, expected in (("major", 22), ("minor", 56)):
        count = session.scalar(select(func.count()).select_from(TarotCard).where(TarotCard.arcana == arcana))
        if count != expected:
            raise ValueError(f"Invalid database arcana distribution: {arcana}")
    if session.scalar(select(func.count()).select_from(CardMeaning)) != 78:
        raise ValueError("Database must contain exactly 78 card meanings")
    return inserted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="Validate metadata without dependencies or a database")
    args = parser.parse_args()
    validate_reference_data()
    if set(MEANINGS) != set(range(1, 79)):
        raise ValueError("Expected one meaning for each of 78 cards")
    if args.check_only:
        print("Validated 78 cards and meanings (22 major / 56 minor), 5 categories, 32 questions, 3 spreads, 18 positions.")
        return

    from sqlalchemy.orm import Session
    from app.database.session import get_engine

    # No create_all, migrations, deletes, or updates are performed by the seed.
    with Session(get_engine()) as session, session.begin():
        inserted = seed_reference_data(session)
    print(f"Inserted {inserted} reference/meaning rows. Artwork paths remain NULL until import.")


if __name__ == "__main__":
    main()
