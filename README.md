# Career Copilot

A personal, single-user career assistant: paste a job description (or send
it from the browser extension), get a tailored one-page resume and cover
letter generated only from your real, stored career history, with a
truth-check pass that flags any claim it can't verify, an ATS score, and a
skill gap analysis. Everything is remembered for next time.

This is intentionally not a general chatbot and not a multi-user product.
It is scoped to one person's job search.

## How it works

1. You paste a job description into the Streamlit app, or send one from
   the browser extension while looking at a posting on LinkedIn, Indeed,
   Handshake, Greenhouse, Lever, Ashby, or Workday.
2. The JD gets parsed into structured fields (company, title, requirements,
   responsibilities, preferred skills) by an LLM call.
3. Your stored resume bullets, projects, skills, and certs are searched
   semantically (vector similarity) for the items most relevant to this JD.
4. A resume and cover letter are generated using ONLY that retrieved
   material, following your writing-style rules (no buzzwords, no em
   dashes, no fake claims).
5. A separate truth-check pass compares every claim in the generated
   resume against your stored source material and flags anything it
   can't verify.
6. You review, edit, and save the final version. Your edits are stored,
   so you can see what you changed over time.
7. You can mark the application's status (applied, referred, interview,
   rejected, etc.) in a simple tracker.

## Project structure

```
career-copilot/
  app/
    app.py              Streamlit UI, the main thing you run
    db.py                SQLite schema and connection helper
    memory.py             Career memory: store + retrieve via embeddings
    llm.py                 Groq API calls and all prompts
    jd_parser.py            Parses raw job text into structured fields
    pipeline.py               Orchestrates ingest -> retrieve -> generate -> check
    backup.py                  Push/pull the SQLite file to/from GitHub
    extension_api.py            Tiny FastAPI receiver for the browser extension
  extension/
    manifest.json               Chrome/Edge extension manifest (V3)
    extractor.js                  Per-site selectors to grab job posting text
    popup.html / popup.js          Extension UI: review text, send to API
    background.js                   Required empty service worker
  scripts/
    seed_from_resume.py             One-time load of your resume into memory
  data/                              SQLite file lives here locally (gitignored)
  requirements.txt
  .streamlit/secrets.toml.example
```

## Local setup

```bash
cd career-copilot
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml, at minimum set GROQ_API_KEY
# (free key at https://console.groq.com)

cd app
python ../scripts/seed_from_resume.py    # loads your resume into memory once
streamlit run app.py
```

Open the URL Streamlit prints (usually http://localhost:8501).

## Running the extension receiver (optional, for the browser extension)

In a second terminal, from the same `app/` directory:

```bash
export GROQ_API_KEY=...          # same key, or read from secrets some other way
export EXTENSION_API_TOKEN=pick-a-random-string
uvicorn extension_api:api --host 0.0.0.0 --port 8765
```

## Installing the browser extension

1. Open `chrome://extensions` (or the Edge equivalent).
2. Enable Developer Mode.
3. Click "Load unpacked" and select the `extension/` folder.
4. Click the extension icon, open Settings, set the API URL
   (`http://localhost:8765` for local use) and the same token you set as
   `EXTENSION_API_TOKEN`.
5. On a job posting page, click the extension icon, then "Extract job
   posting from this page", review the text, then "Send to Career
   Copilot".
6. Switch to the Streamlit app's Generate page to run the actual
   generation (the extension only captures and stores the JD, it
   doesn't trigger generation itself, so you always review before
   spending an API call).

## Deploying to Streamlit Cloud

1. Push this repo to GitHub (a regular public or private repo for the
   code itself).
2. Create a **separate, private** GitHub repo to hold backups of your
   SQLite file, e.g. `career-copilot-data`. Nothing needs to be in it
   initially, the app will create `career.db` in it on first backup.
3. On Streamlit Cloud, create a new app pointed at `app/app.py` in your
   code repo.
4. In the app's Secrets settings, add:
   ```
   GROQ_API_KEY = "..."
   GITHUB_TOKEN = "..."
   GITHUB_REPO = "yourusername/career-copilot-data"
   GITHUB_BRANCH = "main"
   ```
   The GitHub token should be a fine-grained personal access token
   scoped to ONLY the data repo, with read/write access to contents.
5. Deploy. On first run there's no backup yet, so it starts with an
   empty DB, run the seed script's logic manually once via the Memory
   page (add your resume items there), or run the seed script locally
   against the same DB file and let the first backup push it up.

Note: the extension's `extension_api.py` does not run on Streamlit
Cloud (Streamlit Cloud only runs the Streamlit process itself). For the
extension to work against your cloud deployment, run `extension_api.py`
somewhere always-on, your Raspberry Pi, a free Render/Fly.io instance,
or just your laptop while you're actively job hunting. Local-only use
(extension and Streamlit both on your machine) works without this
limitation.

## Why these choices

- **SQLite, not Postgres**: single user, no need for a server process,
  genuinely zero ongoing cost or vendor limits. The tradeoff is the file
  has to live somewhere with persistent disk, handled by the GitHub
  backup step.
- **sqlite-vec, not pgvector**: same vector-search capability, no
  separate database server required.
- **Groq, not local model inference**: free tier, fast, and you don't
  need a GPU. If you later want fully local/offline (e.g. on a Pi with
  no internet dependency), swap `llm.py`'s `_chat()` to call an Ollama
  endpoint instead, the rest of the pipeline doesn't change.
- **One Streamlit process, no separate always-on backend**: simpler to
  deploy and reason about. The only second process is the small
  extension receiver, and that's optional.
- **Truth-check as a separate LLM call, not a single mega-prompt**:
  asking a model to write creatively and fact-check itself in the same
  pass produces weaker checking. Splitting them gives the checker a
  narrower, more reliable job.

## What's intentionally not built yet

Interview prep, recruiter/referral message generation beyond cover
letters, automatic job discovery/crawling, and the "learning from
rejections" loop are all real, valuable features, but they're separate
pieces of work on top of this foundation. This MVP is scoped to: capture
a JD, generate a resume and cover letter from your real history, check
it for honesty, and track the outcome. Once this is working well for
real applications, the natural next additions are recruiter/referral
message templates (reuses the same retrieval + style-rules pattern
already built) and a simple interview question generator (same pattern
again). Job discovery/crawling is the one piece I'd deliberately
deprioritize, since most job boards make scraping difficult or
against their terms, and your existing job alert emails/RSS feeds from
these same sites are a much lower-effort source of "new postings" than
building a crawler.
