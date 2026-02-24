import os
import re
import sqlite3
from typing import Any, Iterable, Optional

try:
    import psycopg2
    from psycopg2 import IntegrityError as PgIntegrityError
except Exception:  # pragma: no cover - optional dependency at runtime
    psycopg2 = None
    PgIntegrityError = Exception

DB_NAME = "proctoring.db"
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
USE_SUPABASE = bool(SUPABASE_DB_URL)

IntegrityError = PgIntegrityError if USE_SUPABASE else sqlite3.IntegrityError


class CompatCursor:
    def __init__(self, cursor, use_postgres: bool):
        self._cursor = cursor
        self._use_postgres = use_postgres

    def _adapt(self, query: str) -> str:
        if not self._use_postgres:
            return query
        return re.sub(r"\?", "%s", query)

    def execute(self, query: str, params: Optional[Iterable[Any]] = None):
        sql = self._adapt(query)
        if params is None:
            self._cursor.execute(sql)
        else:
            self._cursor.execute(sql, tuple(params))
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class CompatConnection:
    def __init__(self, conn, use_postgres: bool):
        self._conn = conn
        self._use_postgres = use_postgres

    def cursor(self):
        return CompatCursor(self._conn.cursor(), self._use_postgres)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def connect(db_name: str = DB_NAME):
    if USE_SUPABASE:
        if psycopg2 is None:
            raise RuntimeError("SUPABASE_DB_URL set but psycopg2 is not installed")
        return CompatConnection(psycopg2.connect(SUPABASE_DB_URL), True)
    return CompatConnection(sqlite3.connect(db_name), False)


def get_db():
    return connect()


def init_db():
    conn = get_db()
    cur = conn.cursor()

    if USE_SUPABASE:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY,
                username TEXT UNIQUE,
                password TEXT,
                role TEXT DEFAULT 'student'
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS questions (
                id BIGSERIAL PRIMARY KEY,
                question TEXT,
                option1 TEXT,
                option2 TEXT,
                option3 TEXT,
                option4 TEXT,
                answer TEXT,
                exam_code TEXT DEFAULT 'DEFAULT'
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS exam_attempts (
                id BIGSERIAL PRIMARY KEY,
                "user" TEXT,
                score INTEGER,
                exam_code TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS violations (
                id BIGSERIAL PRIMARY KEY,
                "user" TEXT,
                exam_code TEXT,
                type TEXT,
                screenshot_path TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS exams (
                id BIGSERIAL PRIMARY KEY,
                exam_code TEXT UNIQUE,
                title TEXT,
                description TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS proctor_health (
                id BIGSERIAL PRIMARY KEY,
                "user" TEXT,
                exam_code TEXT,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    else:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password TEXT,
                role TEXT DEFAULT 'student'
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT,
                option1 TEXT,
                option2 TEXT,
                option3 TEXT,
                option4 TEXT,
                answer TEXT,
                exam_code TEXT DEFAULT 'DEFAULT'
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS exam_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT,
                score INTEGER,
                exam_code TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT,
                exam_code TEXT,
                type TEXT,
                screenshot_path TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS exams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_code TEXT UNIQUE,
                title TEXT,
                description TEXT
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS proctor_health (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT,
                exam_code TEXT,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # SQLite-only lightweight migrations for existing databases
        cur.execute("PRAGMA table_info(questions)")
        question_columns = {row[1] for row in cur.fetchall()}
        if "exam_code" not in question_columns:
            cur.execute("ALTER TABLE questions ADD COLUMN exam_code TEXT DEFAULT 'DEFAULT'")

        cur.execute("PRAGMA table_info(exam_attempts)")
        attempt_columns = {row[1] for row in cur.fetchall()}
        if "exam_code" not in attempt_columns:
            cur.execute("ALTER TABLE exam_attempts ADD COLUMN exam_code TEXT")

        cur.execute("PRAGMA table_info(violations)")
        violation_columns = {row[1] for row in cur.fetchall()}
        if "exam_code" not in violation_columns:
            cur.execute("ALTER TABLE violations ADD COLUMN exam_code TEXT")
        if "screenshot_path" not in violation_columns:
            cur.execute("ALTER TABLE violations ADD COLUMN screenshot_path TEXT")

    conn.commit()
    conn.close()
