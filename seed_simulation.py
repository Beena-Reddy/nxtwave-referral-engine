"""
Simulates the 7-day campaign from docs/growth_plan.md so the dashboard shows
what success (or failure) would look like. Every simulated row is flagged
is_simulated=1 and the dashboard says so — never present these as real users.

  python seed_simulation.py            # simulate (keeps real rows)
  python seed_simulation.py --clear    # delete simulated rows only
  python seed_simulation.py --seed 7   # different random run
"""
import argparse
import random
import sqlite3
import string
from datetime import datetime, timedelta

from app import DB_PATH, init_db, normalize_college

COLLEGES = [normalize_college(c) for c in [
    "Vignan's Institute of Information Technology", "Gokaraju Rangaraju Institute of Engineering",
    "Malla Reddy Engineering College", "Vardhaman College of Engineering",
    "Sri Venkateswara College of Engineering", "KL University", "GITAM University",
    "Anurag University", "CVR College of Engineering", "Vasavi College of Engineering",
    "Sathyabama Institute", "Kongu Engineering College", "Amrita Vishwa Vidyapeetham, Ettimadai",
    "PES University", "RV College of Engineering", "MLR Institute of Technology",
    "Aditya Engineering College", "Lords Institute of Engineering", "SRM AP", "VIT AP",
]]
FIRST = ["Sai", "Harsha", "Divya", "Teja", "Keerthi", "Rahul", "Sneha", "Vamsi", "Pooja", "Arjun",
         "Lakshmi", "Karthik", "Meghana", "Nikhil", "Bhavya", "Ravi", "Anjali", "Manoj", "Swathi",
         "Akhil", "Deepika", "Varun", "Hima", "Charan", "Navya", "Rohit", "Sravani", "Vinay"]
LAST = ["Reddy", "Kumar", "Naidu", "Rao", "Sharma", "Varma", "Krishnan", "Iyer", "Chowdary", "Goud"]
BRANCHES = ["CSE"] * 5 + ["AI/ML / Data Science"] * 2 + ["IT"] * 2 + ["ECE"] * 2 + ["EEE", "Mechanical"]

# Seed (non-referral) registrations planned per channel per day — mirrors docs/growth_plan.md
PLAN = {
    #             D1  D2  D3  D4  D5  D6  D7
    "ambassador": [20, 30, 30, 35, 35, 40, 30],   # 25 ambassadors in class/batch groups
    "club":       [5, 12, 12, 10, 10, 8, 3],      # tech clubs, placement cells
    "linkedin":   [3, 5, 5, 5, 5, 4, 3],
    "telegram":   [2, 3, 4, 4, 3, 3, 1],
    "email":      [0, 0, 6, 0, 0, 6, 0],          # 2 email blasts to past NxtWave leads
}
VISIT_CVR = {"ambassador": 0.42, "club": 0.35, "referral": 0.55, "linkedin": 0.12,
             "telegram": 0.18, "email": 0.08}
REFER_PROB = 0.28      # share of registrants who refer at least one friend
REFS_PER_SHARER = 1.5  # mean friends each sharer brings
HOUR_WEIGHTS = [1, 0, 0, 0, 0, 0, 1, 2, 3, 3, 4, 4, 5, 6, 5, 4, 4, 5, 7, 9, 11, 12, 9, 4]


def code_for(name, used):
    while True:
        c = name[:4].upper() + "-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=4))
        if c not in used:
            used.add(c)
            return c


def ts(day0, d):
    h = random.choices(range(24), weights=HOUR_WEIGHTS)[0]
    return (day0 + timedelta(days=d, hours=h, minutes=random.randint(0, 59),
                             seconds=random.randint(0, 59))).isoformat(timespec="seconds")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clear", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    init_db()
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM registrants WHERE is_simulated=1")
    con.execute("DELETE FROM visits WHERE is_simulated=1")
    con.commit()
    if args.clear:
        print("Simulated data cleared.")
        return

    random.seed(args.seed)
    used = {r[0] for r in con.execute("SELECT ref_code FROM registrants")}
    day0 = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=6)
    people = []          # (ref_code, college, day)
    n = 0

    def add(source, day, referred_by=None, college=None):
        nonlocal n
        n += 1
        fn, ln = random.choice(FIRST), random.choice(LAST)
        name = f"{fn} {ln}"
        college = college or random.choice(COLLEGES)
        code = code_for(fn, used)
        year = random.choices([2027, 2026, 2028], weights=[86, 6, 8])[0]
        con.execute(
            """INSERT INTO registrants (name,email,phone,college,branch,grad_year,city,source,ref_code,
               referred_by,is_simulated,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,1,?)""",
            (name, f"sim{n}.{fn.lower()}@example.com", f"9{random.randint(100000000, 999999999)}",
             college, random.choice(BRANCHES), year, "", source, code, referred_by, ts(day0, day)))
        people.append((code, college, day))
        return code

    for d in range(7):
        # 1) seed channels
        for source, per_day in PLAN.items():
            for _ in range(per_day[d]):
                add(source, d)
        # 2) referral loop: people who joined earlier share; friends are mostly same-college
        new_today = [p for p in people if p[2] == d]
        for code, college, _ in new_today:
            if random.random() < REFER_PROB:
                k = max(1, round(random.expovariate(1 / REFS_PER_SHARER)))
                for _ in range(min(k, 14)):
                    lag = random.choices([0, 1, 2], weights=[55, 35, 10])[0]
                    if d + lag < 7:
                        add("referral", d + lag, referred_by=code,
                            college=college if random.random() < 0.8 else None)

    # visits implied by each channel's conversion rate
    for source, cvr in VISIT_CVR.items():
        for (cnt, day) in con.execute(
                "SELECT COUNT(*), CAST(julianday(date(created_at)) - julianday(?) AS INT) "
                "FROM registrants WHERE is_simulated=1 AND source=? GROUP BY date(created_at)",
                (day0.date().isoformat(), source)).fetchall():
            for _ in range(int(cnt / cvr)):
                con.execute("INSERT INTO visits (source, path, is_simulated, created_at) VALUES (?,?,1,?)",
                            (source, "/", ts(day0, day)))
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM registrants WHERE is_simulated=1").fetchone()[0]
    refd = con.execute("SELECT COUNT(*) FROM registrants WHERE is_simulated=1 AND source='referral'").fetchone()[0]
    print(f"Simulated {total} registrations ({refd} via referrals) over 7 days.")
    con.close()


if __name__ == "__main__":
    main()
