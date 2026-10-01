# LegalEase - AI Legal Document Generator

Streamlit UI + FastAPI backend + Gemini drafting (with an offline template fallback).

## Run
```bash
pip install -r requirements.txt
cp .env.example .env          # add your GEMINI_API_KEY (https://aistudio.google.com/apikey)
streamlit run frontend/app.py            # UI (works on its own)
uvicorn main:app --reload                # optional API on :8000
```
Run both commands from the project root.

## Features
* **Questions depend on the document type** - `ai_core/document_schemas.py`.
* **Before you sign (India)** - the preview page shows stamp-paper, lease-registration (> 1 year), firm-registration,
  non-compete and tax notices (`ai_core/india_legal.py`). 
* **Review for risks** - a button that flags missing or vague clauses (termination, liability, jurisdiction, unfilled
  blanks, ...). Free rule-based checks always run; with a Gemini key an AI pass adds more (`ai_core/review.py`).
* **Tamil / Hindi** - pick a language on the form (needs a Gemini key; the offline template is English only).
* **My documents** - every document is saved automatically (SQLite, `data/legalease.db`); reopen, edit or delete it later.
* **Login + cost limits** - see below.

## Tamil / Hindi PDFs
A font alone is **not enough**: ReportLab cannot shape Indian scripts (vowel signs and conjuncts come out in the wrong
place even with a perfect font). So:
* **DOCX works everywhere** - Word / LibreOffice shape Tamil and Hindi correctly.
* **PDF** is produced with WeasyPrint when it is installed, otherwise the PDF button is disabled with an explanation.
  To enable it: `pip install weasyprint` and install a Noto font - e.g. Ubuntu: `sudo apt install libpango-1.0-0 fonts-noto-core`.
  (Not tested in the development sandbox - open a Tamil and a Hindi PDF and check them by eye before relying on it.)

## Security & cost (read before deploying)
Every Gemini call costs money, so:
1. **Turn login on.** `python auth.py hash-password` -> put the line in `LEGALEASE_USERS`, set `LEGALEASE_REQUIRE_LOGIN=1`.
   For a public site prefer real sign-in (`st.login` with Google/Microsoft, or Cloudflare Access) over a shared password list.
2. **API keys** for `/api/generate` and `/api/review`: `python auth.py new-api-key alice` -> `LEGALEASE_API_KEYS`.
3. **Limits** apply per user (per-minute burst + per-day quota) and **globally** (`LEGALEASE_GLOBAL_DAILY_LIMIT` is your
   spending ceiling). They live in `ai_core/limits.py` and are enforced on *both* the API and the Streamlit UI, so there is
   no back door. Quotas are stored in SQLite and survive restarts. The day resets at midnight IST.
4. Also set a **budget alert / quota in Google AI Studio**, run behind HTTPS, and keep `.env` and `data/` out of git.
5. Documents contain personal data and are sent to Google for drafting. Say so in your privacy notice (India's DPDP Act 2023
   applies to personal data of people in India) and decide how long drafts are kept.

## Config (.env)
See `.env.example` - every variable is documented there.

## Tests
```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```
