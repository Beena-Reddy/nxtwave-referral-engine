"""
Workshop Referral Engine — NxtWave Growth Challenge
Free workshop: "Build Your First AI Project in 60 Minutes"
Goal: 500 final-year engineering registrations in 7 days on a Rs 2,000 budget.

Run:  python app.py   ->  http://localhost:5000
"""
import csv
import io
import json
import os
import random
import re
import sqlite3
import string
import threading
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from flask import (Flask, Response, abort, g, jsonify, redirect,
                   render_template, request, send_from_directory, url_for)

# ---------- config ----------
def load_env(path=".env"):
    if os.path.exists(path):
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

load_env()
DB_PATH = os.environ.get("DB_PATH", "referral.db")
ADMIN_KEY = os.environ.get("ADMIN_KEY", "growth500")
N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
BASE_URL = os.environ.get("BASE_URL", "")  # e.g. https://your-app.onrender.com
TARGET = int(os.environ.get("TARGET", "500"))          # campaign goal (internal)
SEAT_CAP = int(os.environ.get("SEAT_CAP", "1000"))     # live webinar capacity (shown to students)
CAMPAIGN_DAYS = 7
WORKSHOP_TITLE = "Build Your First AI Project in 60 Minutes"
WORKSHOP_DATE = os.environ.get("WORKSHOP_DATE", "Sunday, 11 Oct 2026 · 11:00 AM IST")
WORKSHOP_START = os.environ.get("WORKSHOP_START", "2026-10-11T11:00:00+05:30")  # for calendar invites
WORKSHOP_MINUTES = 60

# Zero-cost rewards for most people; the Rs 2,000 goes ONLY to the top 3.
TIERS = [
    (1, "Session recording + the prompt pack used in the workshop"),
    (3, "'Community Builder' certificate + priority in the live Q&A"),
    (10, "15-minute 1:1 review of your AI project by a NxtWave mentor"),
]
PRIZES = ["₹1,000 voucher", "₹600 voucher", "₹400 voucher"]

SOURCES = {
    "ambassador": "Campus ambassador / class group",
    "referral": "Friend's referral link",
    "club": "Tech club / placement cell",
    "linkedin": "LinkedIn",
    "instagram": "Instagram",
    "telegram": "Telegram / Discord",
    "email": "Email",
    "other": "Other",
}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")


# ---------- database ----------
SCHEMA = """
CREATE TABLE IF NOT EXISTS registrants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NOT NULL UNIQUE,
    college TEXT NOT NULL,
    branch TEXT,
    grad_year INTEGER,
    city TEXT,
    source TEXT,
    ref_code TEXT NOT NULL UNIQUE,
    referred_by TEXT,
    waitlist INTEGER DEFAULT 0,
    is_simulated INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT,
    ref_code TEXT,
    path TEXT,
    is_simulated INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reg_ref ON registrants(referred_by);
CREATE INDEX IF NOT EXISTS idx_reg_created ON registrants(created_at);
CREATE INDEX IF NOT EXISTS idx_vis_created ON visits(created_at);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    cols = [r[1] for r in con.execute("PRAGMA table_info(registrants)")]
    if "waitlist" not in cols:  # upgrade databases created by older versions
        con.execute("ALTER TABLE registrants ADD COLUMN waitlist INTEGER DEFAULT 0")
    con.commit()
    con.close()


# ---------- helpers ----------
def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def normalize_phone(raw):
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]          # +91 98765 43210
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]          # 098765 43210
    return digits


def normalize_college(raw):
    # "  sri venkateswara  college of engg " -> "Sri Venkateswara College Of Engg"
    # "  srm ap ", "SRM AP", "Srm Ap" -> "SRM AP";  "amrita vishwa vidyapeetham , ettimadai" ->
    # "Amrita Vishwa Vidyapeetham, Ettimadai". One spelling per college keeps the leaderboard honest.
    name = re.sub(r"\s+", " ", (raw or "").strip())
    name = re.sub(r"\s*,\s*", ", ", name).strip(", ")
    small = {"of", "and", "the", "for", "in", "at", "&"}
    keep_case = {"sri", "st", "dr"}
    words = []
    for i, w in enumerate(name.split(" ")):
        core = w.strip(",.()").lower()
        if w.isupper() and len(core) <= 5:
            words.append(w)                      # user typed an acronym: keep it
        elif i > 0 and core in small:
            words.append(w.lower())
        elif len(core) <= 3 and core.isalpha() and core not in keep_case and core not in small:
            words.append(w.upper())              # srm, kl, pes, vit, ap -> SRM, KL, PES, VIT, AP
        else:
            words.append(w[:1].upper() + w[1:].lower())
    return " ".join(words)


def make_ref_code(db, name):
    prefix = re.sub(r"[^A-Za-z]", "", name).upper()[:4] or "AI"
    while True:
        code = prefix + "-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        if not db.execute("SELECT 1 FROM registrants WHERE ref_code=?", (code,)).fetchone():
            return code


def base_url():
    return BASE_URL.rstrip("/") or request.host_url.rstrip("/")


def share_message(name, link, college=None):
    who = f" from {college}" if college else ""
    return (
        f"Hey! I just registered for a free 60-min live workshop by NxtWave — "
        f"\"{WORKSHOP_TITLE}\". You leave with a working AI project + GitHub link for your resume, "
        f"which is useful for placements this year.\n\n"
        f"Free, online, {WORKSHOP_DATE}.\nRegister with my link: {link}\n— {name}{who}"
    )


def calendar_url():
    """Google Calendar 'add event' link: a saved calendar slot is the cheapest attendance booster."""
    start = datetime.fromisoformat(WORKSHOP_START).astimezone(timezone.utc)
    end = start + timedelta(minutes=WORKSHOP_MINUTES)
    fmt = "%Y%m%dT%H%M%SZ"
    details = ("Free live workshop by NxtWave. Bring a laptop: you'll build and deploy an AI project. "
               "The joining link will be shared before the session.")
    return ("https://calendar.google.com/calendar/render?action=TEMPLATE"
            f"&text={quote(WORKSHOP_TITLE)}&dates={start.strftime(fmt)}/{end.strftime(fmt)}"
            f"&details={quote(details)}")


@app.context_processor
def inject_globals():
    return {"site_url": base_url(), "title": WORKSHOP_TITLE, "date": WORKSHOP_DATE}


def referral_count(db, code):
    return db.execute("SELECT COUNT(*) FROM registrants WHERE referred_by=?", (code,)).fetchone()[0]


def next_tier(count):
    for need, reward in TIERS:
        if count < need:
            return need, reward
    return None, None


def fire_webhook(payload):
    """Send new registrations to n8n (welcome WhatsApp/email, Google Sheet, reminders)."""
    if not N8N_WEBHOOK_URL:
        return

    def _send():
        try:
            req = urllib.request.Request(
                N8N_WEBHOOK_URL, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:  # never block a registration because automation is down
            app.logger.warning("n8n webhook failed: %s", e)

    threading.Thread(target=_send, daemon=True).start()


def log_visit(source, ref_code, path):
    db = get_db()
    db.execute("INSERT INTO visits (source, ref_code, path, created_at) VALUES (?,?,?,?)",
               (source, ref_code, path, now_iso()))
    db.commit()


# ---------- public pages ----------
@app.route("/")
def index():
    ref = (request.args.get("ref") or "").upper().strip()
    source = (request.args.get("utm_source") or ("referral" if ref else "")).lower()
    db = get_db()
    referrer = None
    if ref:
        referrer = db.execute("SELECT name, college FROM registrants WHERE ref_code=?", (ref,)).fetchone()
        if not referrer:
            ref = ""
    log_visit(source or "direct", ref or None, "/")
    total = db.execute("SELECT COUNT(*) FROM registrants").fetchone()[0]
    colleges = db.execute("SELECT COUNT(DISTINCT college) FROM registrants").fetchone()[0]
    return render_template("index.html", ref=ref, referrer=referrer, source=source,
                           total=total, colleges=colleges, target=SEAT_CAP, full=total >= SEAT_CAP,
                           sources=SOURCES, title=WORKSHOP_TITLE, date=WORKSHOP_DATE,
                           errors={}, form={})


@app.route("/r/<code>")
def short_link(code):
    return redirect(url_for("index", ref=code.upper(), utm_source="referral"))


@app.route("/register", methods=["POST"])
def register():
    db = get_db()
    f = {k: (request.form.get(k) or "").strip() for k in
         ["name", "email", "phone", "college", "branch", "grad_year", "city", "source", "ref"]}
    errors = {}
    if len(f["name"]) < 2:
        errors["name"] = "Enter your full name."
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", f["email"]):
        errors["email"] = "Enter a valid email address."
    phone = normalize_phone(f["phone"])
    if not re.match(r"^[6-9]\d{9}$", phone):
        errors["phone"] = "Enter a 10-digit Indian WhatsApp number."
    if len(f["college"]) < 3:
        errors["college"] = "Enter your college name."
    if f["grad_year"] not in ("2027", "2026", "2028"):
        errors["grad_year"] = "Pick your graduation year."

    email = f["email"].lower()
    # Already registered (same email or same number)? Send them to their page, never double count,
    # even if they filled the rest of the form differently this time.
    if "email" not in errors or "phone" not in errors:
        existing = db.execute("SELECT ref_code FROM registrants WHERE email=? OR phone=?",
                              (email if "email" not in errors else None,
                               phone if "phone" not in errors else None)).fetchone()
        if existing:
            return redirect(url_for("you", code=existing["ref_code"], again=1))

    if errors:
        total = db.execute("SELECT COUNT(*) FROM registrants").fetchone()[0]
        colleges = db.execute("SELECT COUNT(DISTINCT college) FROM registrants").fetchone()[0]
        referrer = None
        if f["ref"]:
            referrer = db.execute("SELECT name, college FROM registrants WHERE ref_code=?",
                                  (f["ref"].upper(),)).fetchone()
        return render_template("index.html", ref=f["ref"], referrer=referrer, source=f["source"],
                               total=total, colleges=colleges, target=SEAT_CAP,
                               full=total >= SEAT_CAP, sources=SOURCES,
                               title=WORKSHOP_TITLE, date=WORKSHOP_DATE, errors=errors, form=f), 400

    ref = f["ref"].upper() or None
    if ref and not db.execute("SELECT 1 FROM registrants WHERE ref_code=?", (ref,)).fetchone():
        ref = None
    source = "referral" if ref else (f["source"] if f["source"] in SOURCES else "other")
    code = make_ref_code(db, f["name"])
    waitlist = 1 if db.execute("SELECT COUNT(*) FROM registrants").fetchone()[0] >= SEAT_CAP else 0
    db.execute(
        """INSERT INTO registrants (name,email,phone,college,branch,grad_year,city,source,
           ref_code,referred_by,waitlist,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (f["name"], email, phone, normalize_college(f["college"]), f["branch"],
         int(f["grad_year"]), f["city"].title(), source, code, ref, waitlist, now_iso()))
    db.commit()

    fire_webhook({
        "event": "registration", "name": f["name"], "email": email, "phone": phone,
        "college": normalize_college(f["college"]), "source": source, "ref_code": code,
        "referred_by": ref, "waitlist": bool(waitlist), "personal_link": f"{base_url()}/r/{code}",
        "workshop": WORKSHOP_TITLE, "date": WORKSHOP_DATE, "created_at": now_iso(),
    })
    return redirect(url_for("you", code=code))


@app.route("/you/<code>")
def you(code):
    db = get_db()
    me = db.execute("SELECT * FROM registrants WHERE ref_code=?", (code.upper(),)).fetchone()
    if not me:
        abort(404)
    count = referral_count(db, me["ref_code"])
    need, reward = next_tier(count)
    rank_row = db.execute("""
        SELECT COUNT(*)+1 FROM (SELECT referred_by, COUNT(*) c FROM registrants
        WHERE referred_by IS NOT NULL GROUP BY referred_by) WHERE c > ?""", (count,)).fetchone()
    link = f"{base_url()}/r/{me['ref_code']}"
    msg = share_message(me["name"].split()[0], link, me["college"])
    college_total = db.execute("SELECT COUNT(*) FROM registrants WHERE college=?",
                               (me["college"],)).fetchone()[0]
    friends = db.execute("SELECT name, college, created_at FROM registrants WHERE referred_by=? "
                         "ORDER BY created_at DESC LIMIT 10", (me["ref_code"],)).fetchall()
    return render_template("you.html", me=me, count=count, need=need, reward=reward,
                           tiers=TIERS, prizes=PRIZES, rank=rank_row[0] if count else None,
                           link=link, wa_url="https://wa.me/?text=" + quote(msg), msg=msg,
                           college_total=college_total, friends=friends,
                           again=request.args.get("again"), ai_enabled=bool(ANTHROPIC_API_KEY),
                           cal_url=calendar_url(),
                           title=WORKSHOP_TITLE, date=WORKSHOP_DATE)


@app.route("/leaderboard")
def leaderboard():
    db = get_db()
    people = db.execute("""
        SELECT r.name, r.college, COUNT(x.id) AS refs
        FROM registrants r JOIN registrants x ON x.referred_by = r.ref_code
        GROUP BY r.id ORDER BY refs DESC, MIN(x.created_at) ASC LIMIT 15""").fetchall()
    colleges = db.execute("""
        SELECT college, COUNT(*) AS regs FROM registrants
        GROUP BY college ORDER BY regs DESC LIMIT 10""").fetchall()
    total = db.execute("SELECT COUNT(*) FROM registrants").fetchone()[0]
    colleges_n = db.execute("SELECT COUNT(DISTINCT college) FROM registrants").fetchone()[0]
    return render_template("leaderboard.html", people=people, colleges=colleges,
                           prizes=PRIZES, total=total, colleges_n=colleges_n)


# ---------- AI: personalised share message ----------
@app.route("/api/pitch/<code>", methods=["POST"])
def ai_pitch(code):
    """Writes a share message tailored to the audience the student picks.
    Uses Claude if ANTHROPIC_API_KEY is set, otherwise a good template."""
    db = get_db()
    me = db.execute("SELECT * FROM registrants WHERE ref_code=?", (code.upper(),)).fetchone()
    if not me:
        abort(404)
    audience = (request.json or {}).get("audience", "class")
    lang = (request.json or {}).get("language", "English")
    link = f"{base_url()}/r/{me['ref_code']}"
    first = me["name"].split()[0]

    templates = {
        "class": share_message(first, link, me["college"]),
        "club": (f"Hi team — sharing a free 60-min live workshop for final-years: \"{WORKSHOP_TITLE}\" "
                 f"by NxtWave ({WORKSHOP_DATE}). Everyone builds and deploys one AI project live. "
                 f"Good fit for our club members before placement season. Register: {link}"),
        "friend": (f"Bro/sis, free workshop on {WORKSHOP_DATE} — we build an actual AI project in 60 min, "
                   f"goes straight on the resume. Join with my link so we're in it together: {link}"),
    }
    fallback = templates.get(audience, templates["class"])
    if not ANTHROPIC_API_KEY:
        return jsonify({"message": fallback, "ai": False})

    prompt = (
        f"Write a WhatsApp message (max 70 words) that a final-year engineering student named {first} "
        f"from {me['college']} ({me['branch'] or 'engineering'}) will send to their {audience} "
        f"group to invite them to a free online workshop: \"{WORKSHOP_TITLE}\" by NxtWave on {WORKSHOP_DATE}. "
        f"Hook: they leave with a deployed AI project + GitHub link for placements. "
        f"Language: {lang} (if not English, write in that language using Roman script mixed naturally with English, "
        f"the way students text). Sound like a student, not an ad. No hashtags, max 1 emoji. "
        f"End with this exact link on its own line: {link}. Output only the message."
    )
    try:
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps({"model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
                             "max_tokens": 300,
                             "messages": [{"role": "user", "content": prompt}]}).encode(),
            headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_API_KEY,
                     "anthropic-version": "2023-06-01"}, method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        text = "".join(b.get("text", "") for b in data.get("content", [])).strip()
        if link not in text:  # guardrail: the link is the whole point
            text += f"\n{link}"
        return jsonify({"message": text, "ai": True})
    except Exception as e:
        app.logger.warning("AI pitch failed: %s", e)
        return jsonify({"message": fallback, "ai": False})


# ---------- growth dashboard (admin) ----------
def require_admin():
    if request.args.get("key") != ADMIN_KEY:
        abort(403)


def compute_stats(db):
    total = db.execute("SELECT COUNT(*) FROM registrants").fetchone()[0]
    visits = db.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
    referred = db.execute("SELECT COUNT(*) FROM registrants WHERE referred_by IS NOT NULL").fetchone()[0]
    sharers = db.execute("SELECT COUNT(DISTINCT referred_by) FROM registrants "
                         "WHERE referred_by IS NOT NULL").fetchone()[0]
    first = db.execute("SELECT MIN(created_at) FROM registrants").fetchone()[0]

    start = datetime.fromisoformat(first).date() if first else datetime.now().date()
    days = [start + timedelta(days=i) for i in range(CAMPAIGN_DAYS)]
    daily = []
    cum = 0
    for i, d in enumerate(days):
        n = db.execute("SELECT COUNT(*) FROM registrants WHERE date(created_at)=?",
                       (d.isoformat(),)).fetchone()[0]
        v = db.execute("SELECT COUNT(*) FROM visits WHERE date(created_at)=?",
                       (d.isoformat(),)).fetchone()[0]
        cum += n
        daily.append({"day": f"Day {i+1}", "date": d.strftime("%d %b"), "regs": n, "visits": v,
                      "cumulative": cum, "target_cum": round(TARGET * PLAN_CURVE[i])})

    by_source = []
    for row in db.execute("SELECT source, COUNT(*) c FROM registrants GROUP BY source ORDER BY c DESC"):
        v = db.execute("SELECT COUNT(*) FROM visits WHERE source=?", (row["source"],)).fetchone()[0]
        by_source.append({"source": row["source"], "label": SOURCES.get(row["source"], row["source"]),
                          "regs": row["c"], "visits": v,
                          "cvr": round(100 * row["c"] / v, 1) if v else None})

    top_colleges = [dict(r) for r in db.execute(
        "SELECT college, COUNT(*) regs FROM registrants GROUP BY college ORDER BY regs DESC LIMIT 8")]
    grad = [dict(r) for r in db.execute(
        "SELECT grad_year, COUNT(*) n FROM registrants GROUP BY grad_year ORDER BY grad_year")]
    hours = [0] * 24
    for r in db.execute("SELECT CAST(strftime('%H', created_at) AS INT) h, COUNT(*) c "
                        "FROM registrants GROUP BY h"):
        hours[r["h"]] = r["c"]

    final_year = sum(x["n"] for x in grad if x["grad_year"] == 2027)
    waitlisted = db.execute("SELECT COUNT(*) FROM registrants WHERE waitlist=1").fetchone()[0]
    return {
        "total": total, "target": TARGET, "visits": visits,
        "conversion": round(100 * total / visits, 1) if visits else 0,
        "referred": referred, "referred_pct": round(100 * referred / total, 1) if total else 0,
        # viral coefficient: new users each existing user brings in
        "k_factor": round(referred / total, 2) if total else 0,
        "share_rate": round(100 * sharers / total, 1) if total else 0,
        "avg_refs_per_sharer": round(referred / sharers, 1) if sharers else 0,
        "final_year_pct": round(100 * final_year / total, 1) if total else 0,
        "colleges": db.execute("SELECT COUNT(DISTINCT college) FROM registrants").fetchone()[0],
        "daily": daily, "by_source": by_source, "top_colleges": top_colleges, "hours": hours,
        "sharers": sharers, "waitlisted": waitlisted, "seat_cap": SEAT_CAP,
        "simulated": db.execute("SELECT COUNT(*) FROM registrants WHERE is_simulated=1").fetchone()[0],
    }


# Planned cumulative share of the 500 by end of each day (see docs/growth_plan.md)
PLAN_CURVE = [0.08, 0.20, 0.34, 0.50, 0.66, 0.84, 1.00]


@app.route("/dashboard")
def dashboard():
    require_admin()
    stats = compute_stats(get_db())
    return render_template("dashboard.html", s=stats, key=ADMIN_KEY, title=WORKSHOP_TITLE)


@app.route("/api/stats")
def api_stats():
    require_admin()
    return jsonify(compute_stats(get_db()))


@app.route("/export.csv")
def export_csv():
    require_admin()
    rows = get_db().execute("SELECT name,email,phone,college,branch,grad_year,city,source,"
                            "ref_code,referred_by,created_at FROM registrants ORDER BY created_at")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name", "email", "phone", "college", "branch", "grad_year", "city", "source",
                "ref_code", "referred_by", "created_at"])
    for r in rows:
        w.writerow(list(r))
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=registrations.csv"})


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "favicon.png", mimetype="image/png")


@app.errorhandler(404)
def not_found(_e):
    return render_template("message.html", heading="That link doesn't exist",
                           body="Check the referral link, or register fresh from the home page."), 404


@app.errorhandler(403)
def forbidden(_e):
    return render_template("message.html", heading="Admin key needed",
                           body="Open the dashboard as /dashboard?key=YOUR_ADMIN_KEY."), 403


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
