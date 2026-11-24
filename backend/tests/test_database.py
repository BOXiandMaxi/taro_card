"""Ephemeral SQLite tests and MySQL offline SQL compilation; never a live DB."""
import importlib.util
import io
from pathlib import Path
import unittest


def initial_migration():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0001_initial_schema.py"
    spec = importlib.util.spec_from_file_location("initial_schema", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def image_filename_migration():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0002_card_image_filename.py"
    spec = importlib.util.spec_from_file_location("image_filename_schema", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def reading_engine_migration():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0003_reading_engine.py"
    spec = importlib.util.spec_from_file_location("reading_engine_schema", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def accounts_migration():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0004_accounts.py"
    spec = importlib.util.spec_from_file_location("accounts_schema", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def analytics_migration():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0005_visitor_analytics.py"
    spec = importlib.util.spec_from_file_location("analytics_schema", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import sqlalchemy
            import alembic
            from app.database.base import Base
            from app import models
        except ModuleNotFoundError as exc:
            raise unittest.SkipTest(f"Backend dependencies unavailable: {exc}") from exc
        cls.base = Base

    def setUp(self):
        from sqlalchemy import create_engine, event
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        self.engine = create_engine("sqlite://")

        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            # SQLite lacks MySQL CHAR_LENGTH; emulate its Unicode semantics.
            connection.create_function("char_length", 1, lambda value: len(value) if value is not None else None)

        with self.engine.begin() as connection:
            context = MigrationContext.configure(connection, opts={"target_metadata": self.base.metadata})
            with Operations.context(context):
                initial_migration().upgrade()
                image_filename_migration().upgrade()
                reading_engine_migration().upgrade()
                accounts_migration().upgrade()
                analytics_migration().upgrade()
        self.addCleanup(self.engine.dispose)

    def seed(self):
        from sqlalchemy.orm import Session
        from database.seeds.seed import seed_reference_data
        with Session(self.engine) as session, session.begin():
            return seed_reference_data(session)

    def reading(self, session):
        from app.models import Reading
        row = Reading(category_id=1, question_id=1, spread_id=1, anonymous_capability_hash="a" * 64)
        session.add(row)
        session.flush()
        return row

    def test_tables_and_metadata_parity(self):
        from sqlalchemy import inspect
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext

        self.assertEqual(len(inspect(self.engine).get_table_names()), 15)
        with self.engine.connect() as connection:
            diff = compare_metadata(MigrationContext.configure(connection), self.base.metadata)
        self.assertEqual(diff, [])

    def test_mysql_offline_sql(self):
        from alembic.migration import MigrationContext
        from alembic.operations import Operations

        output = io.StringIO()
        context = MigrationContext.configure(dialect_name="mysql", opts={
            "as_sql": True, "output_buffer": output, "target_metadata": self.base.metadata,
        })
        with Operations.context(context):
            initial_migration().upgrade()
            accounts_migration().upgrade()
            analytics_migration().upgrade()
        sql = output.getvalue()
        self.assertEqual(sql.count("CREATE TABLE"), 15)
        self.assertIn("ALTER TABLE users ADD COLUMN", sql)
        self.assertIn("CREATE TABLE analytics_page_views", sql)
        self.assertIn("utf8mb4", sql)
        self.assertIn("ON DELETE CASCADE", sql)
        self.assertIn("ON DELETE RESTRICT", sql)
        self.assertIn("ON DELETE SET NULL", sql)
        self.assertIn("`rank` BETWEEN", sql)
        self.assertIn("char_length(trim(custom_question))", sql)

    def test_seed_idempotency_and_editorial_preservation(self):
        from sqlalchemy.orm import Session
        from app.models import TarotCard

        self.assertEqual(self.seed(), 214)
        with Session(self.engine) as session, session.begin():
            session.get(TarotCard, 1).image_path = "/reviewed/local/path.webp"
            session.get(TarotCard, 1).name_th = "ชื่อที่ตรวจทานแล้ว"
        self.assertEqual(self.seed(), 0)
        with Session(self.engine) as session:
            self.assertEqual(session.get(TarotCard, 1).image_path, "/reviewed/local/path.webp")
            self.assertEqual(session.get(TarotCard, 1).name_th, "ชื่อที่ตรวจทานแล้ว")

    def test_seed_collision_rolls_back(self):
        from sqlalchemy.orm import Session
        from sqlalchemy import func, select
        from app.models import TarotCard, Category

        self.seed()
        with Session(self.engine) as session, session.begin():
            session.get(TarotCard, 1).slug = "conflicting-slug"
        with self.assertRaises(ValueError):
            self.seed()
        with Session(self.engine) as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(Category)), 5)

    def test_no_duplicate_draw_cards_or_positions(self):
        from sqlalchemy.orm import Session
        from sqlalchemy.exc import IntegrityError
        from app.models import ReadingCard

        self.seed()
        with Session(self.engine) as session, session.begin():
            reading = self.reading(session)
            session.add(ReadingCard(reading_id=reading.id, position_id=1, card_id=1))
            session.flush()
            for position, card in ((2, 1), (1, 2)):
                with self.assertRaises(IntegrityError), session.begin_nested():
                    session.add(ReadingCard(reading_id=reading.id, position_id=position, card_id=card))
                    session.flush()

    def test_reading_children_cascade_and_references_restrict(self):
        from sqlalchemy.orm import Session
        from sqlalchemy.exc import IntegrityError
        from sqlalchemy import func, select
        from app.models import AIUsageLog, ReadingCard, ReadingInterpretation, TarotCard

        self.seed()
        with Session(self.engine) as session, session.begin():
            reading = self.reading(session)
            session.add_all([
                ReadingCard(reading_id=reading.id, position_id=1, card_id=1),
                ReadingInterpretation(reading_id=reading.id, result={"test": True}, source="database"),
                AIUsageLog(reading_id=reading.id, provider="test", model="test", status="success"),
            ])
            session.flush()
            with self.assertRaises(IntegrityError), session.begin_nested():
                session.delete(session.get(TarotCard, 1))
                session.flush()
            session.delete(reading)
        with Session(self.engine) as session:
            for model in (ReadingCard, ReadingInterpretation):
                self.assertEqual(session.scalar(select(func.count()).select_from(model)), 0)
            self.assertIsNone(session.scalars(select(AIUsageLog)).one().reading_id)

    def test_invalid_status_and_missing_access_rejected(self):
        from sqlalchemy.orm import Session
        from sqlalchemy.exc import IntegrityError
        from app.models import Reading

        self.seed()
        with Session(self.engine) as session, session.begin():
            for kwargs in ({"status": "UNKNOWN", "anonymous_capability_hash": "b" * 64}, {}):
                with self.assertRaises(IntegrityError), session.begin_nested():
                    session.add(Reading(category_id=1, question_id=1, spread_id=1, **kwargs))
                    session.flush()

    def test_custom_question_unicode_length_and_choice(self):
        from sqlalchemy.orm import Session
        from sqlalchemy.exc import IntegrityError
        from app.models import Reading

        self.seed()
        with Session(self.engine) as session, session.begin():
            session.add(Reading(category_id=1, spread_id=1, custom_question="ก" * 1000,
                                anonymous_capability_hash="c" * 64))
            session.flush()
            for question_id, text in ((None, "ก" * 1001), (None, "   "), (1, "คำถามซ้ำ"), (None, None)):
                with self.assertRaises(IntegrityError), session.begin_nested():
                    session.add(Reading(category_id=1, spread_id=1, question_id=question_id,
                                        custom_question=text, anonymous_capability_hash="d" * 64))
                    session.flush()
