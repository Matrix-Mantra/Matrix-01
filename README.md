# Matrix — hospitalsofnepal.com

A simple, Nepali-first web app for finding the right hospital in Nepal.

**Without login** anyone can see the **hospital ranking** (the landing page): every hospital scored on
specialties, 24-hour emergency, health insurance, teaching and referral care, and patient ratings, with
filters, sorting and the method explained on the page. Each hospital page has a location map, departments,
how billing works, how to find your way inside, and ratings and comments from other people.

**After login** (Google sign-in) a person can *speak* their health problem in Nepali (or their animal's:
animal questions get a guide to nearby vets instead of hospitals). Gemini turns the
voice into text, the person checks it, and Gemini then writes a short **downloadable PDF report**:
how urgent it is, what to do now, which department to visit, which hospitals to choose and why,
a map with directions, what to do inside the hospital, how billing works, what to bring and what
to ask the doctor. The report can be downloaded or **sent to the person's email**.

Built for the Google Cloud AI Builder Cup 2026 — theme: **Sustainability & Social Impact**.

## How it works

```
Browser (mobile web, Nepali/English)
  │
  ├─ public:  /api/hospitals, /api/hospitals/{id}    → directory, maps, billing, reviews
  ├─ login:   Firebase Authentication (Google)       → ID token verified on the server
  └─ voice:   record → /api/transcribe               → Gemini speech-to-text (Nepali, Devanagari)
              edit text → /api/report:
                 1. safety rules in code (emergencies can never be missed or overruled)
                 2. Gemini triage            → urgency, department, district (JSON schema)
                 3. hospital search          → our data: department match, distance, ratings
                 4. Gemini report writer     → must choose from our candidate hospitals (JSON schema)
                 5. facts added from data    → billing steps, directions, maps, inside steps
              /api/report/pdf                → WeasyPrint PDF with Nepali font + QR code for directions
Cloud Run (FastAPI) · Firestore (reviews) · Vertex AI Gemini · Firebase Hosting (custom domain)
```

Design choices worth telling the judges:

- **The AI explains, our data decides the facts.** Gemini can only recommend hospitals from the
  candidate list the code built; anything else is dropped. Billing steps, map links and distances
  never come from the model.
- **Emergencies are caught in code.** Chest pain, breathing trouble, stroke signs, snake bite,
  pregnancy bleeding, poisoning, suicidal thoughts and more (English, Nepali, romanized Nepali)
  force an emergency report with a "Call 102" button, even if the model disagrees or is down.
- **Privacy.** Voice and reports are not stored on the server. The PDF is generated on request and
  downloaded to the phone or emailed, then discarded. The database keeps each account's name, email,
  first/last login and login count (to send reports), and reviews. Reviews show first name + initial only.
- **Honest ranking.** Scores come only from listed data, the method and weights are on the page, patient
  ratings count only after 3 reviews, and the page says the scores are not a measure of care quality.
- **Made for laymen.** One big button, Nepali first, the transcript can be corrected before the
  report is made, typing works if speaking doesn't, QR code on the PDF opens directions.

## Project layout

```
app/
  main.py        API routes
  report.py      the report pipeline (safety → triage → search → writer → facts)
  ai.py          Gemini calls: transcription, triage, report writing (structured JSON)
  hospitals.py   directory search, distance, maps links, billing and inside-the-hospital steps
  store.py       reviews and user accounts: SQLite (local) or Firestore (Cloud Run)
  ranking.py     QS-style ranking: indicator scores, weights, tied ranks
  mailer.py      emails the report PDF (SMTP, or .eml files in MAIL_OUTBOX for local testing)
  vets.py        vet search, district government vet office, map search (animal questions)
  auth.py        Firebase token check (or dev login), daily per-user limits
  pdf.py, templates/report.html   PDF report
  safety.py      emergency rules
  data/          hospitals.json, vets.json, departments.json, billing.json, districts.json, schemes.json
static/          the web app (index.html, app.js, i18n.js, styles.css, fonts/) — no build step
scripts/         offline_demo.py, import_osm.py, import_vets.py, build_seed_data.py
docs/pipeline.md the full pipeline, prompts and diagrams (for slides)
eval/            30 test cases + run_eval.py
tests/           automated tests (no API key needed)
```

## Run it on your computer

Needs Python 3.11+, ffmpeg, and Pango (for the PDF):
- macOS: `brew install ffmpeg pango`
- Ubuntu/Debian: `sudo apt install ffmpeg libpango-1.0-0 libpangoft2-1.0-0`
- Windows: easiest is WSL (Ubuntu) and the line above; or use Google Cloud Shell.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env          # paste a free Gemini key from https://aistudio.google.com/apikey
uvicorn app.main:app --reload --port 8080
```

Open http://localhost:8080. Locally, login is "dev mode" (type any name). Microphone recording
needs `localhost` or HTTPS.

No key yet? `python -m scripts.offline_demo` runs the whole app with keyword rules in place of
Gemini — good for working on the design, not for the demo.

## Tests and evaluation

```bash
pytest -q                        # 24 tests: directory, reviews, login, report pipeline, PDF, OSM import
python -m eval.run_eval          # safety rules on 30 cases (offline)
python -m eval.run_eval --live   # Gemini triage on the same cases → eval/results.md
```

## Hospital data — please read

`app/data/hospitals.json` has **68 hospitals** across all 7 provinces with Nepali names. They are
seed data: coordinates, departments and insurance status are **approximate and unverified**, and
the app shows "details being verified" until a row has `"verified": true`.

1. **Add every hospital in Nepal** from OpenStreetMap (run on your computer, needs internet):
   `python -m scripts.import_osm --dry-run`, then without `--dry-run`. New rows have no departments
   yet, so they appear in the directory but are not recommended in reports until you add them.
2. **Verify the hospitals you will demo**: departments, 24-hour emergency, health insurance, phone,
   website. Add `source_url` and set `verified: true`.
3. **Inside-the-hospital directions**: if you know a hospital's layout, add it, e.g.
   `"wayfinding": {"cardiology": "Old building, 2nd floor, room 210"}`, or a photo of the hospital's
   own campus map in `campus_map_url`. Otherwise the app gives general steps and a satellite view.
4. **Billing**: `billing.json` holds the usual process for government, private and community
   hospitals (no prices). Add hospital-specific notes in `billing_notes`.
5. **Reviews start empty.** Ask friends and family to add real reviews of hospitals they've used.
   Never add made-up reviews.

OpenStreetMap data © OpenStreetMap contributors (ODbL). Mukta font: SIL Open Font License (`static/fonts/OFL.txt`).

## Deploy (Cloud Run + Firebase)

1. **Firebase** — at https://console.firebase.google.com add Firebase to your Google Cloud project.
   - Authentication → Sign-in method → enable **Google**.
   - Authentication → Settings → Authorized domains → add `hospitalsofnepal.com` and your `*.run.app` URL.
   - Project settings → Your apps → add a **Web app** → copy apiKey, authDomain, projectId, appId into `.env`.
2. **Deploy** (from macOS/Linux, or Google Cloud Shell):
   ```bash
   gcloud auth login
   ./deploy.sh YOUR_PROJECT_ID
   ```
   This creates Firestore, gives Cloud Run access to Gemini (Vertex AI) and Firestore, and deploys
   with `AUTH_MODE=firebase` and `STORE=firestore`.
3. **Custom domain** —
   ```bash
   npm install -g firebase-tools && firebase login
   firebase use --add YOUR_PROJECT_ID
   firebase deploy --only hosting
   ```
   Firebase console → Hosting → Add custom domain → `hospitalsofnepal.com`, then add the DNS records
   it shows at your domain registrar. DNS can take hours: do this early. After it works, set
   `FIREBASE_AUTH_DOMAIN=hospitalsofnepal.com` and redeploy, so Google login also works in phone
   browsers that block third-party cookies.
4. **Optional map key** — enable "Maps Embed API" (free) in Google Cloud, create an API key restricted
   to your domain, put it in `MAPS_EMBED_API_KEY` and redeploy. The report map then shows the route.
5. **Email (optional)** — put `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` and `MAIL_FROM` in
   `.env` before `./deploy.sh` (Gmail: an App Password from https://myaccount.google.com/apppasswords).
   For a public launch, move the password to Secret Manager rather than a plain environment variable.
6. **Budget alert** — Billing → Budgets & alerts → a few dollars. Each report is two short Gemini calls.

## Scaling notes (for the deck)

- Reviews already live in Firestore; hospital data can move there too when the team needs a CMS.
- Daily usage limits are in memory with one Cloud Run instance. To scale out, move them to Firestore
  or Memorystore and raise `--max-instances`.
- Another country = new hospital data, districts, billing steps and interface text. The pipeline,
  safety pattern and app stay the same.

## Safety statement

Matrix helps people find the right hospital and department. It does not diagnose, prescribe
or give doses, and always tells people to confirm with the hospital. In an emergency, call 102.
