# Workshop Referral Engine

Working asset for the NxtWave Growth Intern challenge: get 500 final-year engineering students to register for **"Build Your First AI Project in 60 Minutes"** in 7 days on ₹2,000.

Instead of a plain landing page, this is the system the growth plan depends on:

| Page | What it does |
|------|--------------|
| `/` | Registration page with live seat counter (1,000-seat webinar cap, then waitlist), referrer banner, source tracking, WhatsApp link-preview card |
| `/r/<code>` | Short personal referral link |
| `/you/<code>` | Personal link, one-tap WhatsApp share, AI-written messages (class / club / friend, 6 Indian languages), Add to Google Calendar, reward ladder, friends who joined |
| `/leaderboard` | Top referrers (top 3 tagged with their prize) and college-vs-college ranking |
| `/dashboard?key=…` | Funnel (visit → register → refer), pacing vs. the 500 plan, channel conversion, K-factor, share rate, % final-year, peak hours, auto-generated insights, CSV export |

Also: duplicate protection (same email or number, including +91 / leading 0), Indian phone validation, college-name cleanup (one spelling per college, acronyms like SRM / KL / VIT kept), n8n webhook on every registration, automatic upgrade of older databases, and a simulator that replays the 7-day plan.

## Folder structure

```
nxtwave-referral-engine/
├── app.py                 # Flask app: routes, DB, referral logic, AI messages, stats
├── seed_simulation.py     # Simulates the 7-day campaign (flagged as simulated)
├── requirements.txt
├── .env.example           # Optional settings (admin key, Claude key, n8n webhook)
├── Procfile / render.yaml # Deployment
├── templates/             # base, index, you, leaderboard, dashboard, message
├── static/                # style.css, chart.umd.min.js (bundled), og.png (WhatsApp preview), favicon.png
└── docs/
    ├── growth_plan.md      # Submission #1 (convert to 2 pages / 5 slides)
    ├── ai_learning_notes.md# Submission #3 (fill in your real examples)
    ├── video_script.md     # Submission #4
    └── n8n_setup.md        # Optional automation
```

## Run it locally (5 minutes)

Needs Python 3.10+.

```bash
# 1. Go into the folder
cd nxtwave-referral-engine

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows:      .venv\Scripts\activate
# Mac / Linux:  source .venv/bin/activate

# 3. Install
pip install -r requirements.txt

# 4. (Optional) settings
cp .env.example .env        # Windows: copy .env.example .env

# 5. Fill the dashboard with the simulated 7-day campaign
python seed_simulation.py

# 6. Start
python app.py
```

Open:
- http://localhost:5000 — registration page
- http://localhost:5000/dashboard?key=growth500 — dashboard (or your `ADMIN_KEY`)
- http://localhost:5000/leaderboard

**Test the referral loop:** register yourself → copy your link from the success page → open it in an incognito window → register a second person → refresh your success page. The count goes to 1 and the first reward unlocks.

**Reset:** `python seed_simulation.py --clear` removes simulated rows only. Delete `referral.db` to wipe everything.

## Turn on AI messages (optional)

Put an Anthropic API key in `.env` as `ANTHROPIC_API_KEY=...` and restart. "Write my message" then generates messages per audience and language (Telugu, Tamil, Hindi, Kannada, Malayalam in Roman script). Without a key it uses solid English templates, so the demo never breaks.

## Deploy a live link (free, ~10 minutes)

1. Push the folder to a new GitHub repo. `.gitignore` already excludes `.env`, the database, `.venv/` and `assg/` (e.g. `github.com/Beena-Reddy/nxtwave-referral-engine`).
2. On [render.com](https://render.com): **New → Blueprint** → pick the repo. `render.yaml` sets everything up (it seeds the simulation on start so reviewers see a full dashboard).
3. After it's live, add env var `BASE_URL=https://<your-app>.onrender.com` so share links and the WhatsApp preview image use the public URL. Change `ADMIN_KEY` too.
4. Submit the live URL plus the dashboard URL with the key.

Free-tier notes: the app sleeps after inactivity (first load takes ~30–50s, so open it before your demo), and the SQLite file resets on redeploy. That's fine for a prototype; for real use, swap SQLite for Postgres.

## Submission checklist

- [ ] **Growth plan:** turn `docs/growth_plan.md` into 2 pages (Google Docs) or 5 slides
- [ ] **Working asset:** live Render link + GitHub repo
- [ ] **AI + learning notes:** rewrite `docs/ai_learning_notes.md` with your real prompts
- [ ] **3-minute video:** follow `docs/video_script.md`, screen-record the demo
- [ ] Submit via the form in the challenge doc within 48 hours
