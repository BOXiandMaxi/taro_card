-- Run once in MySQL as a user allowed to create databases.
-- The application tables and reference data are installed separately by
-- Alembic and database/seeds/seed.py; do not import a second schema dump.
CREATE DATABASE IF NOT EXISTS `tarot_reading`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- Dedicated empty database for automated MySQL tests.
-- Test tables are created and removed by the test fixture.
CREATE DATABASE IF NOT EXISTS `tarot_reading_test`
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
