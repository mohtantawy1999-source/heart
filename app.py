import os, json, logging, traceback
from datetime import date, timedelta
from functools import wraps
from urllib.parse import urlparse

from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash)
from werkzeug.security import generate_password_hash, check_password_hash
import pg8000.native

logging.basicConfig(level=logging.ERROR)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "wird4_secret_2026")
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# ── تواريخ افتراضية (بتتغير من لوحة super admin) ──────────────────
DEFAULT_START   = date(2026, 7, 1)
DEFAULT_END     = date(2026, 7, 7)
DEFAULT_PAGE_START = 1   # أول صفحة قرآن

# ── بيانات الحسابات الأولية ────────────────────────────────────────
INITIAL_ACCOUNTS = {
    "superadmin": [
        {"username": "tantawy",   "password": "159159"},
    ],
    "admin": [
        {"username": "zeyad emad",    "password": "123456789"},
        {"username": "abdo nader",    "password": "123456789"},
        {"username": "mohamed hazem", "password": "123456789"},
        {"username": "omar hesham",   "password": "123456789"},
        {"username": "youssof ramdan","password": "123456789"},
    ],
    "user": [
        {"username": "khaled ayman",        "password": "123456789", "admin": "omar hesham"},
        {"username": "abdalla hany",         "password": "123456789", "admin": "zeyad emad"},
        {"username": "abdelaziz",            "password": "123456789", "admin": "zeyad emad"},
        {"username": "yahia tamer",          "password": "123456789", "admin": "mohamed hazem"},
        {"username": "malek azazy",          "password": "123456789", "admin": "youssof ramdan"},
        {"username": "mohamed mogahed",      "password": "123456789", "admin": "youssof ramdan"},
        {"username": "braa kamel",           "password": "123456789", "admin": "abdo nader"},
        {"username": "ahmed emad",           "password": "123456789", "admin": "abdo nader"},
        {"username": "abdelrahman zakria",   "password": "123456789", "admin": "youssof ramdan"},
        {"username": "ahmed hamada",         "password": "123456789", "admin": "zeyad emad"},
        {"username": "saif elhosiny",        "password": "123456789", "admin": "omar hesham"},
        {"username": "abdalla allam",        "password": "123456789", "admin": "omar hesham"},
        {"username": "mohamed ali",          "password": "123456789", "admin": "mohamed hazem"},
        {"username": "moaz shmais",          "password": "123456789", "admin": "mohamed hazem"},
        {"username": "mohamed salah",        "password": "123456789", "admin": "abdo nader"},
    ],
}

# ── الأوراد الافتراضية مع الدرجات ─────────────────────────────────
DEFAULT_WIRDS = [
    {
        "name": "قراءة 3 صفحات من القرآن",
        "dynamic_pages": True,   # الاسم بيتغير حسب اليوم
        "options": [
            {"code": "done",    "label": "تم القراءة",   "points": 10},
            {"code": "not",     "label": "لم أقرأ",      "points": 0},
        ]
    },
    {
        "name": "صلاة الظهر",
        "dynamic_pages": False,
        "options": [
            {"code": "jam_tak",  "label": "جماعة في المسجد مع تكبيرة الإحرام",    "points": 25},
            {"code": "jam_no",   "label": "جماعة في المسجد بدون تكبيرة الإحرام", "points": 20},
            {"code": "ind_b",    "label": "فردي قبل مرور ساعة من الأذان",         "points": 10},
            {"code": "ind_a",    "label": "فردي بعد مرور ساعة من الأذان",         "points": 5},
            {"code": "not",      "label": "لم أصلِّ",                             "points": 0},
        ]
    },
    {
        "name": "صلاة العصر",
        "dynamic_pages": False,
        "options": [
            {"code": "jam_tak",  "label": "جماعة في المسجد مع تكبيرة الإحرام",    "points": 25},
            {"code": "jam_no",   "label": "جماعة في المسجد بدون تكبيرة الإحرام", "points": 20},
            {"code": "ind_b",    "label": "فردي قبل مرور ساعة من الأذان",         "points": 10},
            {"code": "ind_a",    "label": "فردي بعد مرور ساعة من الأذان",         "points": 5},
            {"code": "not",      "label": "لم أصلِّ",                             "points": 0},
        ]
    },
    {
        "name": "صلاة المغرب",
        "dynamic_pages": False,
        "options": [
            {"code": "jam_tak",  "label": "جماعة في المسجد مع تكبيرة الإحرام",    "points": 25},
            {"code": "jam_no",   "label": "جماعة في المسجد بدون تكبيرة الإحرام", "points": 20},
            {"code": "ind_b",    "label": "فردي قبل مرور ساعة من الأذان",         "points": 10},
            {"code": "ind_a",    "label": "فردي بعد مرور ساعة من الأذان",         "points": 5},
            {"code": "not",      "label": "لم أصلِّ",                             "points": 0},
        ]
    },
    {
        "name": "صلاة العشاء",
        "dynamic_pages": False,
        "options": [
            {"code": "jam_tak",  "label": "جماعة في المسجد مع تكبيرة الإحرام",    "points": 25},
            {"code": "jam_no",   "label": "جماعة في المسجد بدون تكبيرة الإحرام", "points": 20},
            {"code": "ind_b",    "label": "فردي قبل مرور ساعة من الأذان",         "points": 10},
            {"code": "ind_a",    "label": "فردي بعد مرور ساعة من الأذان",         "points": 5},
            {"code": "not",      "label": "لم أصلِّ",                             "points": 0},
        ]
    },
]

# ═══════════════════════════════════════════════════════════════════
# قاعدة البيانات
# ═══════════════════════════════════════════════════════════════════

def get_db():
    p = urlparse(DATABASE_URL)
    return pg8000.native.Connection(
        host=p.hostname, port=p.port or 5432,
        database=p.path.lstrip("/"),
        user=p.username, password=p.password,
        ssl_context=True,
    )

def qone(conn, sql, params=None):
    rows = conn.run(sql, **{f"p{i+1}": v for i, v in enumerate(params or [])})
    if not rows: return None
    cols = [c["name"] for c in conn.columns]
    return dict(zip(cols, rows[0]))

def qall(conn, sql, params=None):
    rows = conn.run(sql, **{f"p{i+1}": v for i, v in enumerate(params or [])})
    if not rows: return []
    cols = [c["name"] for c in conn.columns]
    return [dict(zip(cols, r)) for r in rows]

def qrun(conn, sql, params=None):
    conn.run(sql, **{f"p{i+1}": v for i, v in enumerate(params or [])})


def init_db():
    conn = get_db()

    # ── جداول ──────────────────────────────────────────────────────
    conn.run("""
        CREATE TABLE IF NOT EXISTS site_settings (
            id INTEGER PRIMARY KEY DEFAULT 1,
            site_name    TEXT NOT NULL DEFAULT 'متابعة الأوراد',
            logo_data    TEXT DEFAULT '',
            welcome_msg  TEXT DEFAULT 'أهلاً بك في نظام متابعة الأوراد',
            start_date   TEXT DEFAULT '',
            end_date     TEXT DEFAULT '',
            page_start   INTEGER DEFAULT 1,
            CHECK (id = 1)
        )
    """)

    conn.run("""
        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            username      TEXT UNIQUE NOT NULL,
            password      TEXT NOT NULL,
            plain_pw      TEXT NOT NULL DEFAULT '',
            role          TEXT NOT NULL DEFAULT 'user',
            display_name  TEXT DEFAULT '',
            supervisor_id INTEGER DEFAULT NULL
        )
    """)

    conn.run("""
        CREATE TABLE IF NOT EXISTS wirds (
            id            SERIAL PRIMARY KEY,
            name          TEXT NOT NULL,
            order_num     INTEGER NOT NULL DEFAULT 0,
            active        INTEGER NOT NULL DEFAULT 1,
            dynamic_pages INTEGER NOT NULL DEFAULT 0
        )
    """)

    conn.run("""
        CREATE TABLE IF NOT EXISTS wird_options (
            id       SERIAL PRIMARY KEY,
            wird_id  INTEGER NOT NULL,
            code     TEXT NOT NULL,
            label    TEXT NOT NULL,
            points   INTEGER NOT NULL DEFAULT 0,
            order_num INTEGER NOT NULL DEFAULT 0,
            UNIQUE(wird_id, code)
        )
    """)

    conn.run("""
        CREATE TABLE IF NOT EXISTS records (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER NOT NULL,
            wird_id     INTEGER NOT NULL,
            record_date TEXT NOT NULL,
            option_code TEXT NOT NULL,
            points      INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, wird_id, record_date)
        )
    """)

    conn.run("""
        CREATE TABLE IF NOT EXISTS admin_followup (
            id          SERIAL PRIMARY KEY,
            admin_id    INTEGER NOT NULL,
            user_id     INTEGER NOT NULL,
            follow_date TEXT NOT NULL,
            followed    INTEGER NOT NULL DEFAULT 0,
            score       INTEGER DEFAULT NULL,
            UNIQUE(admin_id, user_id, follow_date)
        )
    """)

    # ── ترقية: أعمدة قد تكون ناقصة في DB قديمة ───────────────────
    for col, dfn in [
        ("display_name",  "TEXT DEFAULT ''"),
        ("supervisor_id", "INTEGER DEFAULT NULL"),
        ("page_start",    "INTEGER DEFAULT 1"),
        ("plain_pw",      "TEXT NOT NULL DEFAULT ''"),
    ]:
        try: conn.run(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {dfn}")
        except Exception: pass
        try: conn.run(f"ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS {col} {dfn}")
        except Exception: pass

    # ── إعدادات الموقع ─────────────────────────────────────────────
    r = qone(conn, "SELECT COUNT(*) as cnt FROM site_settings")
    if r and r["cnt"] == 0:
        qrun(conn, """
            INSERT INTO site_settings (id, site_name, start_date, end_date, page_start)
            VALUES (1, 'متابعة الأوراد', :p1, :p2, :p3)
        """, (DEFAULT_START.isoformat(), DEFAULT_END.isoformat(), DEFAULT_PAGE_START))

    # ── الأوراد الافتراضية ─────────────────────────────────────────
    r = qone(conn, "SELECT COUNT(*) as cnt FROM wirds")
    if r and r["cnt"] == 0:
        for i, w in enumerate(DEFAULT_WIRDS):
            qrun(conn, """
                INSERT INTO wirds (name, order_num, active, dynamic_pages)
                VALUES (:p1, :p2, 1, :p3)
            """, (w["name"], i, 1 if w["dynamic_pages"] else 0))
            wird_row = qone(conn, "SELECT id FROM wirds WHERE name=:p1", (w["name"],))
            if wird_row:
                for j, opt in enumerate(w["options"]):
                    qrun(conn, """
                        INSERT INTO wird_options (wird_id, code, label, points, order_num)
                        VALUES (:p1, :p2, :p3, :p4, :p5)
                        ON CONFLICT (wird_id, code) DO NOTHING
                    """, (wird_row["id"], opt["code"], opt["label"], opt["points"], j))

    # ── الحسابات الأولية ───────────────────────────────────────────
    r = qone(conn, "SELECT COUNT(*) as cnt FROM users WHERE role='superadmin'")
    if r and r["cnt"] == 0:
        # super admins
        for u in INITIAL_ACCOUNTS["superadmin"]:
            qrun(conn, """
                INSERT INTO users (username, password, plain_pw, role, display_name)
                VALUES (:p1,:p2,:p3,'superadmin',:p4)
                ON CONFLICT (username) DO NOTHING
            """, (u["username"], generate_password_hash(u["password"]), u["password"], u["username"]))

        # admins
        for u in INITIAL_ACCOUNTS["admin"]:
            qrun(conn, """
                INSERT INTO users (username, password, plain_pw, role, display_name)
                VALUES (:p1,:p2,:p3,'admin',:p4)
                ON CONFLICT (username) DO NOTHING
            """, (u["username"], generate_password_hash(u["password"]), u["password"], u["username"]))

        # users + ربط كل واحد بـ admin بتاعه
        for u in INITIAL_ACCOUNTS["user"]:
            qrun(conn, """
                INSERT INTO users (username, password, plain_pw, role, display_name)
                VALUES (:p1,:p2,:p3,'user',:p4)
                ON CONFLICT (username) DO NOTHING
            """, (u["username"], generate_password_hash(u["password"]), u["password"], u["username"]))

            admin_row = qone(conn, "SELECT id FROM users WHERE username=:p1", (u["admin"],))
            if admin_row:
                qrun(conn, """
                    UPDATE users SET supervisor_id=:p1
                    WHERE username=:p2
                """, (admin_row["id"], u["username"]))

    conn.close()


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def get_settings(conn):
    s = qone(conn, "SELECT * FROM site_settings WHERE id=1")
    if not s:
        return {"site_name": "متابعة الأوراد", "logo_data": "",
                "welcome_msg": "", "start_date": DEFAULT_START.isoformat(),
                "end_date": DEFAULT_END.isoformat(), "page_start": 1}
    if not s.get("start_date"): s["start_date"] = DEFAULT_START.isoformat()
    if not s.get("end_date"):   s["end_date"]   = DEFAULT_END.isoformat()
    if not s.get("page_start"): s["page_start"] = 1
    return s

def get_period(settings):
    try: sd = date.fromisoformat(settings["start_date"])
    except Exception: sd = DEFAULT_START
    try: ed = date.fromisoformat(settings["end_date"])
    except Exception: ed = DEFAULT_END
    if ed < sd: ed = sd
    return sd, ed

def period_days(sd, ed):
    days, cur = [], sd
    while cur <= ed:
        days.append(cur)
        cur += timedelta(days=1)
    return days

def day_index(d, sd):
    """رقم اليوم في الفترة (يبدأ من 1)"""
    return (d - sd).days + 1

def wird_display_name(wird, d, sd, page_start):
    """لو الورد ديناميكي، يحسب أرقام الصفحات"""
    if not wird.get("dynamic_pages"):
        return wird["name"]
    n = day_index(d, sd)
    p1 = page_start + (n - 1) * 3
    p2, p3 = p1 + 1, p1 + 2
    return f"قراءة 3 صفحات من القرآن  رقم {p1}، {p2}، {p3}"

def get_wirds_with_options(conn):
    wirds = qall(conn, "SELECT * FROM wirds WHERE active=1 ORDER BY order_num")
    for w in wirds:
        w["options"] = qall(conn,
            "SELECT * FROM wird_options WHERE wird_id=:p1 ORDER BY order_num",
            (w["id"],))
    return wirds

def calc_day_score(conn, user_id, d):
    rows = qall(conn, "SELECT points FROM records WHERE user_id=:p1 AND record_date=:p2",
                (user_id, d.isoformat()))
    return sum(r["points"] for r in rows)

def calc_total_score(conn, user_id, sd, ed):
    rows = qall(conn, """
        SELECT SUM(points) as tot FROM records
        WHERE user_id=:p1 AND record_date >= :p2 AND record_date <= :p3
    """, (user_id, sd.isoformat(), ed.isoformat()))
    return (rows[0]["tot"] or 0) if rows else 0

def inject_globals():
    try:
        conn = get_db()
        s = get_settings(conn)
        conn.close()
        return s
    except Exception:
        return {"site_name": "متابعة الأوراد", "logo_data": "", "welcome_msg": "",
                "start_date": DEFAULT_START.isoformat(), "end_date": DEFAULT_END.isoformat(), "page_start": 1}

app.jinja_env.globals.update(site=lambda: inject_globals())

def _get_user_plain(uid):
    try:
        conn = get_db()
        u = qone(conn, "SELECT plain_pw FROM users WHERE id=:p1", (uid,))
        conn.close()
        return u["plain_pw"] if u else "——"
    except Exception:
        return "——"

app.jinja_env.globals.update(get_user_plain=_get_user_plain)


# ── Error handler ──────────────────────────────────────────────────
@app.errorhandler(Exception)
def handle_exc(e):
    logging.error(traceback.format_exc())
    return f"<pre style='padding:20px'>خطأ: {e}\n\n{traceback.format_exc()}</pre>", 500


# ═══════════════════════════════════════════════════════════════════
# Decorators
# ═══════════════════════════════════════════════════════════════════

def login_required(f):
    @wraps(f)
    def dec(*a, **kw):
        if "uid" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return dec

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def dec(*a, **kw):
            r = session.get("role", "")
            if r == "user" and "user" not in roles: pass
            if r not in roles:
                flash("مش عندك صلاحية لهنا", "error")
                return redirect(url_for("index"))
            return f(*a, **kw)
        return dec
    return decorator


# ═══════════════════════════════════════════════════════════════════
# Routes عامة
# ═══════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    if "uid" not in session:
        return redirect(url_for("login"))
    role = session.get("role")
    if role == "superadmin": return redirect(url_for("super_dashboard"))
    if role == "admin":      return redirect(url_for("admin_dashboard"))
    return redirect(url_for("user_dashboard"))


@app.route("/login", methods=["GET", "POST"])
def login():
    conn = get_db()
    settings = get_settings(conn)
    if request.method == "POST":
        uname = request.form.get("username", "").strip()
        pw    = request.form.get("password", "")
        u = qone(conn, "SELECT * FROM users WHERE username=:p1", (uname,))
        conn.close()
        if u and check_password_hash(u["password"], pw):
            session["uid"]      = u["id"]
            session["username"] = u["username"]
            session["role"]     = u["role"]
            session["display"]  = u.get("display_name") or u["username"]
            return redirect(url_for("index"))
        flash("اسم المستخدم أو كلمة السر غلط", "error")
    else:
        conn.close()
    return render_template("login.html", settings=settings)


@app.route("/register", methods=["GET", "POST"])
def register():
    conn = get_db()
    settings = get_settings(conn)
    if request.method == "POST":
        uname = request.form.get("username", "").strip()
        pw    = request.form.get("password", "")
        pw2   = request.form.get("password2", "")
        dname = request.form.get("display_name", "").strip() or uname
        if not uname or not pw:
            flash("اسم المستخدم وكلمة السر مطلوبين", "error")
        elif pw != pw2:
            flash("كلمة السر مش متطابقة", "error")
        elif len(pw) < 4:
            flash("كلمة السر لازم تكون 4 حروف على الأقل", "error")
        else:
            try:
                qrun(conn, """
                    INSERT INTO users (username, password, plain_pw, role, display_name)
                    VALUES (:p1,:p2,:p3,'user',:p4)
                """, (uname, generate_password_hash(pw), pw, dname))
                flash("تم إنشاء الحساب ✅ — يمكنك الدخول الآن", "success")
                conn.close()
                return redirect(url_for("login"))
            except Exception:
                flash("اسم المستخدم ده مستخدم — اختار تاني", "error")
    conn.close()
    return render_template("register.html", settings=settings)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/change_password", methods=["POST"])
@login_required
def change_password():
    old = request.form.get("old_password","")
    new = request.form.get("new_password","")
    new2= request.form.get("new_password2","")
    conn = get_db()
    u = qone(conn, "SELECT * FROM users WHERE id=:p1", (session["uid"],))
    if not check_password_hash(u["password"], old):
        flash("كلمة السر القديمة غلط ❌", "error")
    elif new != new2:
        flash("التأكيد مش متطابق ❌", "error")
    elif len(new) < 4:
        flash("كلمة السر لازم 4 حروف على الأقل", "error")
    else:
        qrun(conn, "UPDATE users SET password=:p1, plain_pw=:p2 WHERE id=:p3",
             (generate_password_hash(new), new, session["uid"]))
        flash("تم تغيير كلمة السر ✅", "success")
    conn.close()
    role = session.get("role")
    if role == "superadmin": return redirect(url_for("super_dashboard"))
    if role == "admin":      return redirect(url_for("admin_dashboard"))
    return redirect(url_for("user_dashboard"))


@app.route("/change_username", methods=["POST"])
@login_required
def change_username():
    new_uname = request.form.get("new_username","").strip()
    if not new_uname:
        flash("اكتب اسم المستخدم الجديد", "error")
    else:
        conn = get_db()
        try:
            qrun(conn, "UPDATE users SET username=:p1 WHERE id=:p2", (new_uname, session["uid"]))
            session["username"] = new_uname
            flash("تم تغيير اسم المستخدم ✅", "success")
        except Exception:
            flash("الاسم ده مستخدم بالفعل", "error")
        conn.close()
    role = session.get("role")
    if role == "superadmin": return redirect(url_for("super_dashboard"))
    if role == "admin":      return redirect(url_for("admin_dashboard"))
    return redirect(url_for("user_dashboard"))


# ═══════════════════════════════════════════════════════════════════
# صفحة المستخدم (user)
# ═══════════════════════════════════════════════════════════════════

@app.route("/user", methods=["GET","POST"])
@login_required
@role_required("user")
def user_dashboard():
    today = date.today()
    conn  = get_db()
    s     = get_settings(conn)
    sd, ed = get_period(s)
    days   = period_days(sd, ed)
    wirds  = get_wirds_with_options(conn)
    page_start = s.get("page_start") or 1

    # اليوم المختار
    sel_str = request.args.get("date","")
    try:
        sel = date.fromisoformat(sel_str)
        if not (sd <= sel <= ed): raise ValueError
    except Exception:
        sel = max(sd, min(today, ed))

    if request.method == "POST":
        action = request.form.get("action","save")
        if action == "save":
            rd_str = request.form.get("record_date", sel.isoformat())
            try:
                rd = date.fromisoformat(rd_str)
                if not (sd <= rd <= ed): rd = sel
            except Exception:
                rd = sel
            for w in wirds:
                code = request.form.get(f"w_{w['id']}")
                opt  = next((o for o in w["options"] if o["code"] == code), None)
                if opt:
                    qrun(conn, """
                        INSERT INTO records (user_id,wird_id,record_date,option_code,points)
                        VALUES (:p1,:p2,:p3,:p4,:p5)
                        ON CONFLICT (user_id,wird_id,record_date)
                        DO UPDATE SET option_code=EXCLUDED.option_code, points=EXCLUDED.points
                    """, (session["uid"], w["id"], rd.isoformat(), code, opt["points"]))
            flash(f"تم حفظ أوراد {rd.strftime('%d/%m')} ✅","success")
            conn.close()
            return redirect(url_for("user_dashboard", date=rd.isoformat()))

    # سجلات اليوم المختار
    recs = qall(conn,
        "SELECT wird_id,option_code,points FROM records WHERE user_id=:p1 AND record_date=:p2",
        (session["uid"], sel.isoformat()))
    selected = {r["wird_id"]: r for r in recs}

    # إحصائيات كل أيام الفترة
    stats = []
    for d in days:
        dr = qall(conn,
            "SELECT wird_id,option_code,points FROM records WHERE user_id=:p1 AND record_date=:p2",
            (session["uid"], d.isoformat()))
        day_rec = {r["wird_id"]: r for r in dr}
        day_pts = sum(r["points"] for r in dr)
        stats.append({
            "date": d, "records": day_rec,
            "points": day_pts, "missing": len(wirds) - len(dr),
        })

    total_pts = calc_total_score(conn, session["uid"], sd, ed)

    # مشرف
    sup = None
    u = qone(conn, "SELECT supervisor_id FROM users WHERE id=:p1", (session["uid"],))
    if u and u.get("supervisor_id"):
        sup = qone(conn, "SELECT username,display_name FROM users WHERE id=:p1", (u["supervisor_id"],))

    conn.close()
    return render_template("user_dashboard.html",
        s=s, wirds=wirds, selected=selected, sel=sel, today=today,
        sd=sd, ed=ed, stats=stats, total_pts=total_pts, sup=sup,
        page_start=page_start,
        wird_name=lambda w,d: wird_display_name(w, d, sd, page_start))


# ═══════════════════════════════════════════════════════════════════
# صفحة الـ admin
# ═══════════════════════════════════════════════════════════════════

@app.route("/admin", methods=["GET","POST"])
@login_required
@role_required("admin")
def admin_dashboard():
    today = date.today()
    conn  = get_db()
    s     = get_settings(conn)
    sd, ed = get_period(s)
    days   = period_days(sd, ed)
    wirds  = get_wirds_with_options(conn)
    page_start = s.get("page_start") or 1

    # Users تحت إشراف هذا الـ admin
    users = qall(conn,
        "SELECT id,username,display_name FROM users WHERE supervisor_id=:p1 ORDER BY display_name",
        (session["uid"],))

    # اليوم المختار
    sel_str = request.args.get("date","")
    try:
        sel = date.fromisoformat(sel_str)
        if not (sd <= sel <= ed): raise ValueError
    except Exception:
        sel = max(sd, min(today, ed))

    if request.method == "POST":
        action = request.form.get("action","")

        # تغيير كلمة سر user
        if action == "reset_user_pw":
            uid_t = request.form.get("user_id")
            new_pw = request.form.get("new_pw","").strip()
            # تأكد إن الـ user ده فعلاً تحت إشراف هذا الـ admin
            own = qone(conn, "SELECT id FROM users WHERE id=:p1 AND supervisor_id=:p2",
                       (uid_t, session["uid"]))
            if own and new_pw and len(new_pw) >= 4:
                qrun(conn, "UPDATE users SET password=:p1, plain_pw=:p2 WHERE id=:p3",
                     (generate_password_hash(new_pw), new_pw, uid_t))
                flash("تم تغيير كلمة السر ✅","success")
            else:
                flash("خطأ في البيانات","error")

        # تسجيل المتابعة والتقييم
        elif action == "save_followup":
            fu_date = request.form.get("fu_date", sel.isoformat())
            for u in users:
                fol = 1 if request.form.get(f"fol_{u['id']}") else 0
                sc_str = request.form.get(f"score_{u['id']}","").strip()
                sc = int(sc_str) if sc_str.isdigit() and 0 <= int(sc_str) <= 100 else None
                qrun(conn, """
                    INSERT INTO admin_followup (admin_id,user_id,follow_date,followed,score)
                    VALUES (:p1,:p2,:p3,:p4,:p5)
                    ON CONFLICT (admin_id,user_id,follow_date)
                    DO UPDATE SET followed=EXCLUDED.followed, score=EXCLUDED.score
                """, (session["uid"], u["id"], fu_date, fol, sc))
            flash(f"تم حفظ المتابعة ليوم {fu_date} ✅","success")

        conn.close()
        return redirect(url_for("admin_dashboard", date=sel.isoformat()))

    # تقرير كل user لكل يوم
    report = []
    for u in users:
        udata = {"user": u, "days": [], "total_pts": 0}
        for d in days:
            dr = qall(conn,
                "SELECT wird_id,option_code,points FROM records WHERE user_id=:p1 AND record_date=:p2",
                (u["id"], d.isoformat()))
            day_rec = {r["wird_id"]: r for r in dr}
            day_pts = sum(r["points"] for r in dr)

            fu = qone(conn,
                "SELECT followed,score FROM admin_followup WHERE admin_id=:p1 AND user_id=:p2 AND follow_date=:p3",
                (session["uid"], u["id"], d.isoformat()))

            udata["days"].append({
                "date": d, "records": day_rec,
                "points": day_pts, "missing": len(wirds) - len(dr),
                "fu": fu
            })
            udata["total_pts"] += day_pts
        report.append(udata)

    # متابعة اليوم المختار
    sel_followup = {}
    for u in users:
        fu = qone(conn,
            "SELECT followed,score FROM admin_followup WHERE admin_id=:p1 AND user_id=:p2 AND follow_date=:p3",
            (session["uid"], u["id"], sel.isoformat()))
        sel_followup[u["id"]] = fu

    conn.close()
    return render_template("admin_dashboard.html",
        s=s, users=users, wirds=wirds, report=report,
        sel=sel, today=today, sd=sd, ed=ed, days=days,
        sel_followup=sel_followup, page_start=page_start,
        wird_name=lambda w,d: wird_display_name(w, d, sd, page_start))


# ═══════════════════════════════════════════════════════════════════
# صفحة الـ super admin
# ═══════════════════════════════════════════════════════════════════

@app.route("/super", methods=["GET","POST"])
@login_required
@role_required("superadmin")
def super_dashboard():
    conn = get_db()
    s    = get_settings(conn)
    sd, ed = get_period(s)
    wirds  = get_wirds_with_options(conn)

    if request.method == "POST":
        action = request.form.get("action","")

        # ── إعدادات الموقع ──────────────────────────────────────
        if action == "update_site":
            site_name = request.form.get("site_name","").strip()
            welcome   = request.form.get("welcome_msg","").strip()
            logo_file = request.files.get("logo_file")
            updates = {}
            if site_name: updates["site_name"] = site_name
            if welcome:   updates["welcome_msg"] = welcome
            if logo_file and logo_file.filename:
                import base64
                ext = logo_file.filename.rsplit(".",1)[-1].lower()
                if ext in ("png","jpg","jpeg","svg","webp"):
                    mime = {"png":"image/png","jpg":"image/jpeg","jpeg":"image/jpeg",
                            "svg":"image/svg+xml","webp":"image/webp"}[ext]
                    b64 = base64.b64encode(logo_file.read()).decode()
                    updates["logo_data"] = f"data:{mime};base64,{b64}"
            if updates:
                sc = ", ".join(f"{k}=:p{i+1}" for i,k in enumerate(updates))
                qrun(conn, f"UPDATE site_settings SET {sc} WHERE id=1", list(updates.values()))
                flash("تم حفظ إعدادات الموقع ✅","success")

        elif action == "remove_logo":
            qrun(conn, "UPDATE site_settings SET logo_data='' WHERE id=1")
            flash("تم حذف اللوجو","success")

        elif action == "update_period":
            try:
                new_sd = date.fromisoformat(request.form.get("start_date",""))
                new_ed = date.fromisoformat(request.form.get("end_date",""))
                new_ps = int(request.form.get("page_start","1"))
                if new_ed < new_sd: raise ValueError
                qrun(conn, """
                    UPDATE site_settings SET start_date=:p1, end_date=:p2, page_start=:p3 WHERE id=1
                """, (new_sd.isoformat(), new_ed.isoformat(), new_ps))
                flash(f"تم تحديث الفترة: {new_sd.strftime('%d/%m/%Y')} – {new_ed.strftime('%d/%m/%Y')} ✅","success")
            except Exception:
                flash("بيانات الفترة غلط","error")

        # ── إدارة المستخدمين ─────────────────────────────────────
        elif action == "add_user":
            uname = request.form.get("username","").strip()
            pw    = request.form.get("password","").strip()
            role  = request.form.get("role","user")
            dname = request.form.get("display_name","").strip() or uname
            sup_id= request.form.get("supervisor_id","") or None
            if uname and pw and role in ("user","admin","superadmin"):
                try:
                    qrun(conn, """
                        INSERT INTO users (username,password,plain_pw,role,display_name,supervisor_id)
                        VALUES (:p1,:p2,:p3,:p4,:p5,:p6)
                    """, (uname, generate_password_hash(pw), pw, role, dname, sup_id))
                    flash(f"تم إضافة '{uname}' ✅","success")
                except Exception:
                    flash("الاسم ده موجود","error")

        elif action == "delete_user":
            uid_t = request.form.get("user_id")
            qrun(conn, "DELETE FROM users WHERE id=:p1 AND role!='superadmin'", (uid_t,))
            flash("تم الحذف","success")

        elif action == "reset_pw":
            uid_t  = request.form.get("user_id")
            new_pw = request.form.get("new_pw","").strip()
            if new_pw and len(new_pw) >= 4:
                qrun(conn, "UPDATE users SET password=:p1, plain_pw=:p2 WHERE id=:p3",
                     (generate_password_hash(new_pw), new_pw, uid_t))
                flash("تم تغيير كلمة السر ✅","success")

        elif action == "update_supervisor":
            uid_t  = request.form.get("user_id")
            sup_id = request.form.get("supervisor_id","") or None
            qrun(conn, "UPDATE users SET supervisor_id=:p1 WHERE id=:p2", (sup_id, uid_t))
            flash("تم تحديث المشرف ✅","success")

        # ── إدارة الأوراد ─────────────────────────────────────────
        elif action == "add_wird":
            wname = request.form.get("wird_name","").strip()
            dyn   = 1 if request.form.get("dynamic_pages") else 0
            if wname:
                r = qone(conn,"SELECT MAX(order_num) as mx FROM wirds")
                mx = r["mx"] if r and r["mx"] is not None else 0
                qrun(conn, "INSERT INTO wirds (name,order_num,active,dynamic_pages) VALUES (:p1,:p2,1,:p3)",
                     (wname, mx+1, dyn))
                flash("تم إضافة الورد ✅","success")

        elif action == "edit_wird":
            wid   = request.form.get("wird_id")
            wname = request.form.get("wird_name","").strip()
            dyn   = 1 if request.form.get("dynamic_pages") else 0
            if wid and wname:
                qrun(conn, "UPDATE wirds SET name=:p1, dynamic_pages=:p2 WHERE id=:p3",
                     (wname, dyn, wid))
                flash("تم تعديل الورد ✅","success")

        elif action == "delete_wird":
            wid = request.form.get("wird_id")
            qrun(conn, "UPDATE wirds SET active=0 WHERE id=:p1", (wid,))
            flash("تم حذف الورد","success")

        # ── إدارة خيارات الورد ────────────────────────────────────
        elif action == "add_option":
            wid    = request.form.get("wird_id")
            code   = request.form.get("opt_code","").strip().replace(" ","_")
            label  = request.form.get("opt_label","").strip()
            points = request.form.get("opt_points","0").strip()
            if wid and code and label:
                r = qone(conn,"SELECT MAX(order_num) as mx FROM wird_options WHERE wird_id=:p1",(wid,))
                mx = r["mx"] if r and r["mx"] is not None else 0
                try:
                    qrun(conn, """
                        INSERT INTO wird_options (wird_id,code,label,points,order_num)
                        VALUES (:p1,:p2,:p3,:p4,:p5)
                        ON CONFLICT (wird_id,code) DO UPDATE SET label=EXCLUDED.label, points=EXCLUDED.points
                    """, (wid, code, label, int(points) if points.isdigit() else 0, mx+1))
                    flash("تم إضافة الخيار ✅","success")
                except Exception as ex:
                    flash(f"خطأ: {ex}","error")

        elif action == "edit_option":
            oid    = request.form.get("opt_id")
            label  = request.form.get("opt_label","").strip()
            points = request.form.get("opt_points","0").strip()
            if oid and label:
                qrun(conn, "UPDATE wird_options SET label=:p1, points=:p2 WHERE id=:p3",
                     (label, int(points) if points.isdigit() else 0, oid))
                flash("تم تعديل الخيار ✅","success")

        elif action == "delete_option":
            oid = request.form.get("opt_id")
            qrun(conn, "DELETE FROM wird_options WHERE id=:p1", (oid,))
            flash("تم حذف الخيار","success")

        conn.close()
        return redirect(url_for("super_dashboard"))

    # GET
    all_users  = qall(conn, "SELECT * FROM users WHERE role='user'    ORDER BY display_name")
    all_admins = qall(conn, "SELECT * FROM users WHERE role='admin'   ORDER BY display_name")
    all_super  = qall(conn, "SELECT * FROM users WHERE role='superadmin' ORDER BY display_name")

    # تقرير إجمالي كل users
    days = period_days(sd, ed)
    report_users = []
    for u in all_users:
        tot = calc_total_score(conn, u["id"], sd, ed)
        sup = qone(conn,"SELECT display_name FROM users WHERE id=:p1",(u["supervisor_id"],)) if u.get("supervisor_id") else None
        report_users.append({**u, "total_pts": tot, "sup_name": sup["display_name"] if sup else "—"})

    # تقرير إجمالي كل admins (مجموع درجات الـ users اللي تحتهم)
    report_admins = []
    for a in all_admins:
        my_users = qall(conn,"SELECT id FROM users WHERE supervisor_id=:p1",(a["id"],))
        group_pts = sum(calc_total_score(conn, u["id"], sd, ed) for u in my_users)
        report_admins.append({**a, "group_pts": group_pts, "user_count": len(my_users)})

    conn.close()
    return render_template("super_dashboard.html",
        s=s, wirds=wirds, all_users=all_users, all_admins=all_admins,
        all_super=all_super, report_users=report_users,
        report_admins=report_admins, sd=sd, ed=ed)


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
