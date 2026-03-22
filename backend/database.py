import sqlite3

DB_NAME = "proctoring.db"

def get_db():
    return sqlite3.connect(DB_NAME)

def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT DEFAULT 'student'
    )
    """)

    # Questions
    cur.execute("""
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
    """)

    # Exam Attempts
    cur.execute("""
    CREATE TABLE IF NOT EXISTS exam_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        score INTEGER,
        exam_code TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Violations
    cur.execute("""
    CREATE TABLE IF NOT EXISTS violations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        exam_code TEXT,
        type TEXT,
        screenshot_path TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Exams
    cur.execute("""
    CREATE TABLE IF NOT EXISTS exams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_code TEXT UNIQUE,
        title TEXT,
        description TEXT
    )
    """)

    # Proctor heartbeat health
    cur.execute("""
    CREATE TABLE IF NOT EXISTS proctor_health (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user TEXT,
        exam_code TEXT,
        last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Lightweight migrations for existing databases
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
