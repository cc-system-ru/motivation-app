import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fio TEXT NOT NULL,
    position TEXT NOT NULL,
    level INTEGER DEFAULT 1,
    dept TEXT NOT NULL,
    salary REAL DEFAULT 0,
    active INTEGER DEFAULT 1,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    closed INTEGER DEFAULT 0,
    closed_at TEXT,
    UNIQUE(year, month)
);

CREATE TABLE IF NOT EXISTS payroll (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    period_id INTEGER NOT NULL,
    inputs TEXT NOT NULL,
    calc TEXT NOT NULL,
    total REAL DEFAULT 0,
    paid REAL DEFAULT 0,
    saved INTEGER DEFAULT 0,
    updated_at TEXT,
    UNIQUE(employee_id, period_id)
);

CREATE TABLE IF NOT EXISTS settings (
    position TEXT PRIMARY KEY,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    actor TEXT,
    action TEXT,
    detail TEXT
);
"""


def now():
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        db.executescript(SCHEMA)
        seed_employees(db)


def seed_employees(db):
    rows = db.execute("SELECT COUNT(*) c FROM employees").fetchone()["c"]
    if rows:
        return
    from config import POSITIONS
    seed = [
        ("Руслан", "kd", 1, 100000),
        ("Вадим", "mop", 1, 35000),
        ("Данил", "mop", 1, 35000),
        ("Александр", "mop", 2, 45000),
        ("Антон", "mop", 2, 45000),
        ("Владимир", "od", 1, 90000),
        ("Мамий Инвер", "and", 1, 45000),
        ("Серёгин Евгений", "and", 1, 45000),
        ("Щербань Дмитрий", "and", 1, 45000),
        ("Кирсанов Данил", "and_sr", 1, 50000),
        ("Иванов Иван", "rep", 1, 50000),
        ("Сергей Васильевич", "sb", 1, 20000),
        ("Мария Иванова", "adm", 1, 45000),
    ]
    for fio, pos, level, salary in seed:
        db.execute(
            "INSERT INTO employees (fio, position, level, dept, salary, active, created_at)"
            " VALUES (?,?,?,?,?,1,?)",
            (fio, pos, level, POSITIONS[pos][1], salary, now()),
        )


def current_period(db):
    row = db.execute(
        "SELECT * FROM periods ORDER BY year DESC, month DESC LIMIT 1"
    ).fetchone()
    if row:
        return row
    from datetime import date
    t = date.today()
    db.execute(
        "INSERT INTO periods (year, month, closed) VALUES (?,?,0)", (t.year, t.month)
    )
    return db.execute(
        "SELECT * FROM periods ORDER BY id DESC LIMIT 1"
    ).fetchone()


def get_period(db, period_id):
    return db.execute("SELECT * FROM periods WHERE id=?", (period_id,)).fetchone()


def ensure_period(db, year, month):
    row = db.execute(
        "SELECT * FROM periods WHERE year=? AND month=?", (year, month)
    ).fetchone()
    if row:
        return row
    db.execute("INSERT INTO periods (year, month, closed) VALUES (?,?,0)", (year, month))
    return db.execute(
        "SELECT * FROM periods WHERE year=? AND month=?", (year, month)
    ).fetchone()


def get_settings(db, position, defaults):
    row = db.execute("SELECT data FROM settings WHERE position=?", (position,)).fetchone()
    if not row:
        return defaults
    saved = json.loads(row["data"])
    merged = json.loads(json.dumps(defaults))
    merged.update(saved)
    return merged


def save_settings(db, position, data):
    db.execute(
        "INSERT INTO settings (position, data) VALUES (?,?)"
        " ON CONFLICT(position) DO UPDATE SET data=excluded.data",
        (position, json.dumps(data, ensure_ascii=False)),
    )


def log(db, actor, action, detail=""):
    db.execute(
        "INSERT INTO audit (ts, actor, action, detail) VALUES (?,?,?,?)",
        (now(), actor, action, detail),
    )
