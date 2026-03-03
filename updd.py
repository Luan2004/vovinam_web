import sqlite3
import os
import random
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'sinhvien.db')


def get_december_dates(year=2025, month=12):
    """Danh sách tất cả ngày trong tháng"""
    start = date(year, month, 1)
    dates = []
    d = start
    while d.month == month:
        dates.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return dates


def seed_attendance_december_2025():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 🔑 Lấy danh sách MSSV
    c.execute("SELECT mssv FROM sinhvien WHERE role='user'")
    mssvs = [r[0] for r in c.fetchall()]

    if not mssvs:
        print("❌ Không có sinh viên")
        return

    dates = get_december_dates(2025, 12)

    records = []

    for mssv in mssvs:
        # mỗi sinh viên điểm danh ngẫu nhiên 8–18 ngày
        attended_days = random.sample(
            dates,
            k=random.randint(8, min(18, len(dates)))
        )
        for d in attended_days:
            records.append((mssv, d))

    # 🔥 INSERT
    c.executemany("""
        INSERT OR IGNORE INTO attendance (mssv, date)
        VALUES (?, ?)
    """, records)

    conn.commit()
    conn.close()

    print(f"✔ Đã seed {len(records)} lượt điểm danh tháng 12/2025")


if __name__ == "__main__":
    seed_attendance_december_2025()
