# db.py
import sqlite3
import hashlib
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'sinhvien.db')


def hash_password(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ================== TABLE SINHVIEN ==================
    c.execute("""
        CREATE TABLE IF NOT EXISTS sinhvien (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            mssv TEXT NOT NULL UNIQUE,
            gmail TEXT,
            password TEXT NOT NULL,
            role TEXT CHECK(role IN ('admin','user')) NOT NULL DEFAULT 'user'
        )
    """)

    # UNIQUE gmail (chỉ khi NOT NULL)
    c.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_gmail
        ON sinhvien(gmail)
        WHERE gmail IS NOT NULL
    """)

    # ================== TABLE ATTENDANCE ==================
    c.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mssv TEXT NOT NULL,
            date TEXT NOT NULL,
            UNIQUE(mssv, date)
        )
    """)

    # Index tối ưu truy vấn điểm danh
    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_attendance_mssv
        ON attendance(mssv)
    """)

    c.execute("""
        CREATE INDEX IF NOT EXISTS idx_attendance_date
        ON attendance(date)
    """)

    conn.commit()
    conn.close()


def seed_data():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.executemany("""
        INSERT OR IGNORE INTO sinhvien
        (full_name, mssv, gmail, password, role)
        VALUES (?, ?, NULL, ?, 'user')
    """, [(name, mssv, default_password) for name, mssv in students])

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    seed_data()
    print("✔ Database initialized (sinhvien + attendance)")
