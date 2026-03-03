#urls.py
from jinja2 import Environment, FileSystemLoader
import os
import re
import sqlite3
from urllib.parse import parse_qs
import json
import random
import smtplib
from email.mime.text import MIMEText
from datetime import date, datetime
from zoneinfo import ZoneInfo
import math
import hashlib
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'sinhvien.db')

# Cấu hình Jinja2
template_dir = os.path.join(os.path.dirname(__file__), 'html')
env = Environment(loader=FileSystemLoader(template_dir))

def response(body=b'', status='200 OK', headers=None):
    if headers is None:
        headers = []
    if not any(h[0].lower() == 'content-type' for h in headers):
        headers.append(('Content-Type', 'text/html; charset=utf-8'))
    return body, status, headers

def json_response(data, status='200 OK'):
    return (
        json.dumps(data, ensure_ascii=False).encode(),
        status,
        [('Content-Type', 'application/json; charset=utf-8')]
    )

# Hàm render template
def render_template(template_name, environ=None, **kwargs):
    role = ''
    if environ:
        role = get_cookie(environ, 'role') or ''

    template = env.get_template(template_name)
    body = template.render(role=role, **kwargs).encode()

    return body, '200 OK', [('Content-Type', 'text/html; charset=utf-8')]


# View function
def home_view(environ):
    qs = parse_qs(environ.get('QUERY_STRING', ''))
    msg = qs.get('logout', [''])[0]

    message = None
    if msg == '1':
        message = "✅ Bạn đã đăng xuất"

    return render_template('home.html', environ, message=message)


def admin_required(view):
    def wrapper(environ):
        role = get_cookie(environ, 'role')
        if role != 'admin':
            return response(
                status='302 Found',
                headers=[('Location', '/login')]
            )
        return view(environ)
    return wrapper

@admin_required
def delete_user_view(environ):
    if environ['REQUEST_METHOD'] != 'POST':
        return response(
            b'405 Method Not Allowed',
            '405 Method Not Allowed'
        )

    size = int(environ.get('CONTENT_LENGTH', 0) or 0)
    data = parse_qs(environ['wsgi.input'].read(size).decode())

    user_id = data.get('user_id', [''])[0]
    if not user_id.isdigit():
        return response(b'Invalid ID', '400 Bad Request')

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT role FROM sinhvien WHERE id=?", (user_id,))
    row = c.fetchone()
    if row and row[0] == 'admin':
        conn.close()
        return response(
            "Không thể xóa admin".encode('utf-8'),
            '403 Forbidden'
        )


    c.execute("DELETE FROM sinhvien WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

    return response(status='302 Found', headers=[('Location', '/admin')])


@admin_required
def admin_view(environ):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Lấy từ khóa tìm kiếm (GET)
    qs = parse_qs(environ.get('QUERY_STRING', ''))
    q = qs.get('q', [''])[0].strip()

    message = None

    # Xử lý POST: tạo user
    if environ['REQUEST_METHOD'] == 'POST':
        size = int(environ.get('CONTENT_LENGTH', 0) or 0)
        data = parse_qs(environ['wsgi.input'].read(size).decode())

        if 'full_name' in data:
            full_name = data['full_name'][0].strip()
            mssv = data['mssv'][0].strip()
            password = data['password'][0]
            gmail = data.get('gmail', [''])[0] or None

            hashed = hashlib.sha256(password.encode()).hexdigest()

            try:
                c.execute("""
                    INSERT INTO sinhvien (full_name, mssv, gmail, password, role)
                    VALUES (?, ?, ?, ?, ?)
                """, (full_name, mssv, gmail, hashed, 'user'))
                conn.commit()
                message = "✅ Tạo tài khoản thành công"
            except sqlite3.IntegrityError:
                message = "❌ MSSV đã tồn tại"

    # Truy vấn danh sách user với điều kiện tìm kiếm
    if q:
        c.execute("""
            SELECT id, full_name, mssv, gmail, role
            FROM sinhvien
            WHERE LOWER(full_name) LIKE ?
            ORDER BY id DESC
        """, (f"%{q.lower()}%",))
    else:
        c.execute("""
            SELECT id, full_name, mssv, gmail, role
            FROM sinhvien
            ORDER BY id DESC
        """)
    users = c.fetchall()
    conn.close()

    # Render template, truyền cả q để giữ ô tìm kiếm
    return render_template(
        'admin.html',
        environ,
        users=users,
        message=message,
        q=q
    )

def login_required(view):
    def wrapper(environ):
        user_id = get_cookie(environ, 'user_id')
        if not user_id:
            return response(
                status='302 Found',
                headers=[('Location', '/login?msg=not_login')]
            )

        return view(environ)
    return wrapper

def login_view(environ):
    if environ['REQUEST_METHOD'] == 'GET':
        qs = parse_qs(environ.get('QUERY_STRING', ''))
        msg = qs.get('msg', [''])[0]

        error = None
        if msg == 'not_login':
            error = "⚠️ Bạn cần đăng nhập để sử dụng chức năng này"

        return render_template('login.html', environ, error=error)

    # ===== POST =====
    size = int(environ.get('CONTENT_LENGTH', 0) or 0)
    data = parse_qs(environ['wsgi.input'].read(size).decode())

    mssv = data.get('mssv', [''])[0].strip()
    password = data.get('password', [''])[0]
    hashed = hashlib.sha256(password.encode()).hexdigest()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1️⃣ Kiểm tra MSSV
    c.execute("""
        SELECT id, password, role
        FROM sinhvien
        WHERE mssv=?
    """, (mssv,))
    row = c.fetchone()

    if not row:
        conn.close()
        return render_template(
            'login.html',
            environ,
            error="❌ Sai mã số sinh viên"
        )

    user_id, db_password, role = row

    # 2️⃣ Kiểm tra mật khẩu
    if db_password != hashed:
        conn.close()
        return render_template(
            'login.html',
            environ,
            error="❌ Sai mật khẩu"
        )

    conn.close()

    # 3️⃣ Đăng nhập thành công
    headers = [
        ('Set-Cookie', f'user_id={user_id}; Path=/; SameSite=Lax'),
        ('Set-Cookie', f'role={role}; Path=/; SameSite=Lax'),
        ('Location', '/admin' if role == 'admin' else '/')
    ]

    return b'', '302 Found', headers


def logout_view(environ):
    headers = [
        ('Set-Cookie', 'user_id=; Path=/; Max-Age=0; SameSite=Lax'),
        ('Set-Cookie', 'role=; Path=/; Max-Age=0; SameSite=Lax'),
        ('Cache-Control', 'no-store'),
        ('Pragma', 'no-cache'),
        ('Location', '/?logout=1')
    ]
    return b'', '302 Found', headers

@login_required
def attendance_view(environ):
    return render_template('attendance.html', environ)

@login_required
def attendance_api(environ):
    user_id = get_cookie(environ, 'user_id')
    if not user_id or not user_id.isdigit():
        return json_response([], '401 Unauthorized')

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 🔑 Lấy MSSV từ user_id
    c.execute("SELECT mssv FROM sinhvien WHERE id=?", (user_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return json_response([], '400 Bad Request')

    mssv = row[0]

    # 🔑 Truy vấn theo MSSV
    c.execute("""
        SELECT date FROM attendance
        WHERE mssv = ?
    """, (mssv,))
    rows = c.fetchall()
    conn.close()

    events = [{
        "title": "✓",
        "start": d[0],
        "display": "list-item",   # ⭐ QUAN TRỌNG
        "textColor": "green"
    } for d in rows]



    return json_response(events)

# Vị trí tại sân tập clb
TARGET_LAT = 10.046690007167342
TARGET_LNG = 105.76769287644787

# Vị trí tại trọ
# TARGET_LAT = 10.055232082480675
# TARGET_LNG = 105.75391796104408
MAX_DISTANCE = 50  # mét


def calc_distance_haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # bán kính Trái Đất (m)

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(dlambda / 2) ** 2

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def attendance_checkin_api(environ):
    user_id = get_cookie(environ, 'user_id')
    if not user_id or not user_id.isdigit():
        return json_response(
            {"ok": False, "msg": "Bạn chưa đăng nhập"},
            '401 Unauthorized'
        )

    try:
        size = int(environ.get('CONTENT_LENGTH') or 0)
        raw = environ['wsgi.input'].read(size).decode('utf-8') if size > 0 else ''

        if not raw:
            return json_response(
                {"ok": False, "msg": "Dữ liệu gửi lên rỗng"},
                '400 Bad Request'
            )

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return json_response(
                {"ok": False, "msg": "JSON không hợp lệ"},
                '400 Bad Request'
            )

        # ===== BẮT BUỘC CÓ GPS =====
        for k in ('lat', 'lng'):
            if k not in data:
                return json_response(
                    {"ok": False, "msg": f"Thiếu dữ liệu {k}"},
                    '400 Bad Request'
                )

        lat = float(data['lat'])
        lng = float(data['lng'])
        accuracy = float(data.get('accuracy', 999))

        # ===== TIME VN =====
        now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
        today = now.strftime("%Y-%m-%d")

        if data.get('date') != today:
            return json_response(
                {"ok": False, "msg": "Sai ngày điểm danh"},
                '400 Bad Request'
            )

        if not (now.hour > 18 or (now.hour == 18 and now.minute >= 30) and now.hour < 22):
            return json_response(
                {"ok": False, "msg": "Chỉ được điểm danh từ 18:30 đến 22:00"},
                '403 Forbidden'
            )

        if accuracy > 80:
            return json_response(
                {"ok": False, "msg": "GPS yếu, vui lòng ra nơi thoáng"},
                '400 Bad Request'
            )

        distance = calc_distance_haversine(lat, lng, TARGET_LAT, TARGET_LNG)
        if distance + accuracy > MAX_DISTANCE + 20:
            return json_response(
                {"ok": False, "msg": f"Ngoài phạm vi ({int(distance)}m ±{int(accuracy)}m)"},
                '403 Forbidden'
            )

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()

        c.execute("SELECT mssv FROM sinhvien WHERE id=?", (user_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return json_response(
                {"ok": False, "msg": "Tài khoản không tồn tại"},
                '400 Bad Request'
            )

        mssv = row[0]

        c.execute("""
            INSERT OR IGNORE INTO attendance (mssv, date)
            VALUES (?, ?)
        """, (mssv, today))

        if c.rowcount == 0:
            conn.close()
            return json_response(
                {"ok": False, "msg": "Bạn đã điểm danh hôm nay"},
                '409 Conflict'
            )

        conn.commit()
        conn.close()

        return json_response({
            "ok": True,
            "distance": int(distance),
            "accuracy": int(accuracy)
        })

    except Exception as e:
        return json_response(
            {"ok": False, "error": str(e)},
            '500 Internal Server Error'
        )

def get_cookie(environ, name):
    cookies = environ.get('HTTP_COOKIE', '')
    for c in cookies.split(';'):
        if '=' in c:
            k, v = c.strip().split('=', 1)
            if k == name:
                return v or ''
    return ''

@login_required
def account_view(environ):
    user_id = get_cookie(environ, 'user_id')

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    message = None

    if environ['REQUEST_METHOD'] == 'POST':
        size = int(environ.get('CONTENT_LENGTH', 0) or 0)
        data = parse_qs(environ['wsgi.input'].read(size).decode('utf-8'))

        phone = data.get('phone', [''])[0].strip()
        phone_norm = phone.replace(' ', '').replace('.', '')

        phone_db = phone_norm if phone_norm else None

        # Validate: sai thì KHÔNG update
        if phone_norm and not re.fullmatch(r'0\d{9,10}', phone_norm):
            message = "❌ Số điện thoại không hợp lệ (phải bắt đầu bằng 0 và 10-11 số)"
        else:
            try:
                c.execute("""
                    UPDATE sinhvien
                    SET gmail=?
                    WHERE id=?
                """, (phone_db, user_id))
                conn.commit()
                message = "✅ Cập nhật số điện thoại thành công"
            except sqlite3.IntegrityError:
                message = "❌ Số điện thoại đã tồn tại"

    # Luôn load user ở đây (GET/POST đều có)
    c.execute("""
        SELECT full_name, mssv, gmail
        FROM sinhvien
        WHERE id=?
    """, (user_id,))
    user = c.fetchone()
    conn.close()

    if not user:
        return response(b'User not found', '404 Not Found')

    return render_template(
        'account.html',
        environ,
        user={'full_name': user[0], 'mssv': user[1], 'gmail': user[2]},
        message=message
    )

@login_required
def change_password_view(environ):
    user_id = get_cookie(environ, 'user_id')
    message = None

    if environ['REQUEST_METHOD'] == 'POST':
        size = int(environ.get('CONTENT_LENGTH', 0) or 0)
        data = parse_qs(environ['wsgi.input'].read(size).decode())

        pw1 = data.get('password', [''])[0]
        pw2 = data.get('confirm_password', [''])[0]

        if pw1 != pw2:
            message = "❌ Mật khẩu không khớp"
        elif len(pw1) < 4:
            message = "❌ Mật khẩu tối thiểu 4 ký tự"
        else:
            hashed = hashlib.sha256(pw1.encode()).hexdigest()

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute(
                "UPDATE sinhvien SET password=? WHERE id=?",
                (hashed, user_id)
            )
            conn.commit()
            conn.close()

            message = "✅ Đổi mật khẩu thành công"

    return render_template(
        'change_password.html',
        environ,
        message=message
    )

@admin_required
def admin_edit_user_view(environ):
    qs = parse_qs(environ.get('QUERY_STRING', ''))
    user_id = qs.get('id', [''])[0]

    if not user_id.isdigit():
        return response(b'Invalid ID', '400 Bad Request')

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    message = None

    # ================== HANDLE POST ==================
    if environ['REQUEST_METHOD'] == 'POST':
        size = int(environ.get('CONTENT_LENGTH', 0) or 0)
        data = parse_qs(environ['wsgi.input'].read(size).decode('utf-8'))

        full_name = data.get('full_name', [''])[0].strip()
        mssv = data.get('mssv', [''])[0].strip()
        gmail_raw = data.get('gmail', [''])[0].strip()

        # 🔑 RẤT QUAN TRỌNG
        gmail = gmail_raw if gmail_raw else None

        try:
            c.execute("""
                UPDATE sinhvien
                SET full_name = ?, mssv = ?, gmail = ?
                WHERE id = ? AND role != 'admin'
            """, (full_name, mssv, gmail, user_id))

            conn.commit()
            message = "✅ Cập nhật thành công"

        except sqlite3.IntegrityError as e:
            # debug rõ lỗi (MSSV hay Gmail)
            if "mssv" in str(e):
                message = "❌ MSSV đã tồn tại"
            elif "gmail" in str(e):
                message = "❌ Gmail đã tồn tại"
            else:
                message = f"❌ Lỗi dữ liệu: {e}"

    # ================== LOAD USER ==================
    c.execute("""
        SELECT id, full_name, mssv, gmail
        FROM sinhvien
        WHERE id = ?
    """, (user_id,))
    row = c.fetchone()
    conn.close()

    if not row:
        return response(b'User not found', '404 Not Found')

    return render_template(
        'admin_edit_user.html',
        environ,
        user={
            'id': row[0],
            'full_name': row[1],
            'mssv': row[2],
            'gmail': row[3]
        },
        message=message
    )

@admin_required
def attendance_stats_view(environ):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    qs = parse_qs(environ.get('QUERY_STRING', ''))
    today = date.today()

    # ===== LẤY YEAR / MONTH TỪ QUERY =====
    try:
        year = int(qs.get('year', [today.year])[0])
    except:
        year = today.year

    try:
        month = int(qs.get('month', [today.month])[0])
    except:
        month = today.month

    if month < 1 or month > 12:
        month = today.month

    # ===== LẤY DANH SÁCH NĂM CÓ ĐIỂM DANH =====
    c.execute("""
        SELECT DISTINCT strftime('%Y', date)
        FROM attendance
        ORDER BY date DESC
    """)
    years = [int(r[0]) for r in c.fetchall()]

    # Nếu chưa có dữ liệu điểm danh nào
    if not years:
        years = [today.year]

    # Nếu năm được chọn không tồn tại trong DB
    if year not in years:
        year = years[0]

    ym = f"{year}-{month:02d}"

    # ===== BIỂU ĐỒ =====
    c.execute("""
        SELECT strftime('%d', date) AS day,
               COUNT(DISTINCT mssv)
        FROM attendance
        WHERE strftime('%Y-%m', date) = ?
        GROUP BY day
        ORDER BY day
    """, (ym,))
    rows = c.fetchall()

    days = [r[0] for r in rows]
    counts = [r[1] for r in rows]

    # ===== CLICK DETAIL =====
    c.execute("""
        SELECT strftime('%d', a.date), s.full_name
        FROM attendance a
        JOIN sinhvien s ON a.mssv = s.mssv
        WHERE strftime('%Y-%m', a.date) = ?
        ORDER BY s.full_name
    """, (ym,))
    detail_rows = c.fetchall()

    day_details = {}
    for d, name in detail_rows:
        day_details.setdefault(d, []).append(name)

    # ===== TABLE =====
    c.execute("""
        SELECT s.full_name, s.mssv, COUNT(a.id)
        FROM sinhvien s
        LEFT JOIN attendance a
          ON s.mssv = a.mssv
         AND strftime('%Y-%m', a.date) = ?
        GROUP BY s.mssv
        ORDER BY COUNT(a.id) DESC
    """, (ym,))
    member_counts = c.fetchall()

    conn.close()

    return render_template(
        'attendance_stats.html',
        environ,
        year=year,
        month=month,
        years=years,                 # ✅ NĂM THẬT SỰ CÓ DỮ LIỆU
        days=json.dumps(days),
        counts=json.dumps(counts),
        day_details=json.dumps(day_details),
        member_counts=member_counts
    )

@admin_required
def admin_search_user_api(environ):
    qs = parse_qs(environ.get('QUERY_STRING', ''))
    q = qs.get('q', [''])[0].strip().lower()

    if not q:
        return json_response([])

    conn = sqlite3.connect(DB_PATH)
    conn.create_function("reverse", 1, lambda s: s[::-1])
    c = conn.cursor()

    c.execute("""
        SELECT id, full_name
        FROM sinhvien
        WHERE LOWER(
          TRIM(
            substr(full_name,
                   length(full_name) - instr(reverse(full_name), ' ') + 2)
          )
        ) LIKE ?
        ORDER BY full_name
        LIMIT 10
    """, (f"%{q}%",))

    rows = c.fetchall()
    conn.close()

    return json_response([
        {"id": r[0], "full_name": r[1]}
        for r in rows
    ])

# Bảng định tuyến
routes = {
    '/': home_view,
    '/login': login_view,
    '/logout': logout_view, 
    '/attendance': attendance_view,
    '/api/attendance': attendance_api,
    '/api/attendance/checkin': attendance_checkin_api,
    '/admin': admin_view,
    '/admin/delete-user': delete_user_view,
    '/account': account_view,
    '/change-password': change_password_view,
    '/admin/edit-user': admin_edit_user_view,
    '/admin/attendance-stats' : attendance_stats_view,
    '/admin/search-user': admin_search_user_api,

}
