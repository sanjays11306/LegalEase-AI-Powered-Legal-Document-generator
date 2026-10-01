"""LegalEase - AI Legal Document Generator (Streamlit UI).

Flow: home -> details (fields depend on the document type) -> preview -> edit -> final (download).
Run: streamlit run frontend/app.py
"""
import html as htmllib
import os
import re
import sys
from datetime import date
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components

# Make project-root packages (ai_core, exporters) importable when running `streamlit run frontend/app.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auth  # noqa: E402
from ai_core import (DESCRIPTIONS, DOCUMENT_TYPES, GROUP_ORDER, GenResult, generate_document,  # noqa: E402
                     get_fields, missing_required)
from ai_core import storage  # noqa: E402
from ai_core.gemini_generator import LANGUAGES  # noqa: E402
from ai_core.india_legal import notices as india_notices  # noqa: E402
from ai_core.limits import (RateLimitExceeded, burst, check_and_consume, check_input_size,  # noqa: E402
                            daily_limit, usage_today)
from ai_core.review import review_document  # noqa: E402
from exporters import document_utils as du  # noqa: E402
from styles import load_css  # noqa: E402

# Custom live editor (plain HTML/JS component, no build step): the preview updates on every keystroke
EDITOR = components.declare_component("legalease_editor", path=str(Path(__file__).parent / "editor_component"))
# Optional remote API (e.g. http://127.0.0.1:8000/api/generate). Empty = generate inside this app.
API_URL = os.getenv("LEGALEASE_API_URL", "").strip()

LOGO = Path(__file__).parent / "assets" / "legalease_logo.png"
DISCLAIMER = ("LegalEase generates documents for informational purposes and does not provide legal advice. "
              "Review documents carefully and consult a qualified legal professional when appropriate.")

st.set_page_config(page_title="LegalEase - Legal Document Generator", page_icon="⚖️", layout="wide")

# ---------------------------------------------------------------- state
DEFAULTS = {"page": "home", "doc_type": None, "eff_date": None, "form_values": {},
            "original_doc": "", "edited_doc": "", "editor_text": "", "editor_token": 0, "last_save_nonce": 0,
            "source": "", "model": "", "warning": "", "edit_error": False,
            "user": None, "language": "English", "doc_id": None, "review": None, "notice_details": {},
            "save_error": "", "confirm_delete": None}
for k, v in DEFAULTS.items():
    st.session_state.setdefault(k, v)


class GenerationRefused(Exception):
    """The remote API said no (bad key, rate limit, invalid input). Never worked around by generating locally."""


def request_document(doc_type: str, details: dict, eff: date, language: str, user: str) -> GenResult:
    """Draft a document. Uses the remote API only if LEGALEASE_API_URL is set; otherwise (or if that server
    cannot be reached) it generates here. Every path is input-size checked and quota limited, so there is no
    back door around the cost limits."""
    if API_URL:
        try:
            r = requests.post(API_URL, json={"doc_type": doc_type, "details": details, "effective_date": eff.isoformat(),
                                             "language": language},
                              headers={"X-API-Key": os.getenv("LEGALEASE_API_KEY", "")}, timeout=300)
            if r.status_code == 200:
                data = r.json()
                return GenResult(data["document"], data["source"], data.get("model", ""), data.get("warning", ""))
            if r.status_code in (401, 403, 422, 429):
                try:
                    detail = r.json().get("detail", "")
                except ValueError:
                    detail = ""
                raise GenerationRefused(detail if isinstance(detail, str) and detail else f"The server refused the request ({r.status_code}).")
        except requests.RequestException:
            pass    # server unreachable -> generate here (still limited below)
    check_input_size(details)
    check_and_consume(user, "generate")
    return generate_document(doc_type, details, eff, language=language)


def persist() -> None:
    """Save (or update) the current document in 'My documents'. Best effort: a disk problem never blocks the user."""
    ss = st.session_state
    try:
        ss.doc_id = storage.save_document(ss.user, ss.doc_type or "Legal document", ss.edited_doc, ss.notice_details,
                                          ss.language, ss.eff_date.isoformat() if ss.eff_date else "", ss.doc_id)
        ss.save_error = ""
    except Exception as exc:
        ss.save_error = f"Could not save a copy to My documents ({type(exc).__name__})."


def open_saved(doc_id: int) -> None:
    """Callback: load a saved draft into the preview page."""
    ss = st.session_state
    d = storage.get_document(ss.user, doc_id)
    if not d:
        return
    for k in [k for k in ss if str(k).startswith("w_")]:
        del ss[k]
    ss.doc_type, ss.language = d.doc_type, d.language if d.language in LANGUAGES else "English"
    ss.eff_date = _to_date(d.effective_date) or date.today()
    ss.form_values = {d.doc_type: dict(d.details)} if d.details else {}
    ss.original_doc = ss.edited_doc = d.text
    ss.notice_details, ss.doc_id, ss.review = dict(d.details), d.id, None
    ss.source, ss.model, ss.warning, ss.save_error = "saved", "", "", ""
    ss.page = "preview"


def delete_saved(doc_id: int) -> None:
    ss = st.session_state
    if ss.confirm_delete != doc_id:
        ss.confirm_delete = doc_id      # first click only asks for confirmation
        return
    storage.delete_document(ss.user, doc_id)
    if ss.doc_id == doc_id:
        ss.doc_id = None
    ss.confirm_delete = None


def run_review() -> None:
    """Callback for 'Review for risks': free rule checks always, plus a Gemini pass when a key is set and quota allows."""
    ss = st.session_state
    key = os.getenv("GEMINI_API_KEY", "").strip()
    use_ai, note = bool(key) and key != "your_api_key", ""
    if use_ai:
        try:
            check_and_consume(ss.user, "review")
        except RateLimitExceeded as exc:
            use_ai, note = False, f"{exc} Showing the automatic checks only."
    res = review_document(ss.doc_type or "", ss.edited_doc, key if use_ai else "", ss.language)
    ss.review = {"issues": res.issues, "ai": res.ai_used, "model": res.model, "warning": note or res.warning,
                 "for": hash(ss.edited_doc)}


def sign_out() -> None:
    st.session_state.clear()


def go(page: str) -> None:
    """Callback: switch page (runs before the rerun so widgets pick up new state)."""
    ss = st.session_state
    if page == "edit":
        ss.edit_error = False
        ss.editor_text = ss.edited_doc
        ss.editor_token += 1  # tells the editor component to load fresh text (and ignore stale values)
    ss.page = page


def current_editor_text() -> str:
    """Latest text from the live editor - but only if it belongs to the current editing session."""
    ss = st.session_state
    live = ss.get("editor")
    if isinstance(live, dict) and live.get("token") == ss.editor_token and "text" in live:
        return live["text"]
    return ss.editor_text


def commit_edit(text: str) -> bool:
    """Store edited text and open the final page. Never saves an empty document."""
    ss = st.session_state
    if not text.strip():
        ss.edit_error = True
        return False
    ss.edit_error = False
    ss.edited_doc = text
    ss.page = "final"
    persist()
    return True


def save_changes() -> None:
    """Callback for the Save button in the sticky bar."""
    commit_edit(current_editor_text())


def new_document() -> None:
    """Callback: forget the current document and start with an empty form."""
    ss = st.session_state
    ss.original_doc = ss.edited_doc = ""
    ss.doc_id, ss.review, ss.notice_details = None, None, {}
    ss.form_values, ss.doc_type, ss.eff_date = {}, None, None
    for k in [k for k in ss if str(k).startswith("w_")]:
        del ss[k]
    ss.page = "generator"


# ---------------------------------------------------------------- login
def require_login() -> None:
    """Stop here until the visitor is signed in. With no users configured and LEGALEASE_REQUIRE_LOGIN off, the app
    runs in open 'local' mode (development)."""
    ss = st.session_state
    if ss.user:
        return
    if not auth.login_required():
        ss.user = auth.LOCAL_USER
        return
    _, mid, _ = st.columns([1, 2, 1])
    mid.image(str(LOGO), width=420)
    page_title("Sign in", "Sign in to create and save legal documents")
    with st.form("login"):
        name = st.text_input("Username")
        pw = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")
    if submitted:
        who = name.strip().lower()
        wait = burst.hit(f"login:{who}", 5, 600) or burst.hit("login:*", 40, 600)   # slow down password guessing
        if wait:
            st.error(f"Too many sign-in attempts. Please wait about {max(1, wait // 60)} minute(s).")
        elif auth.authenticate(name, pw):
            ss.user = name.strip()
            st.rerun()
        else:
            st.error("Wrong username or password.")
    footer()
    st.stop()


# ---------------------------------------------------------------- shared UI
def header(back: bool = True) -> None:
    left, _, right = st.columns([3, 3, 4], vertical_alignment="center")
    left.image(str(LOGO), width=200)
    if back:
        r1, r2 = right.columns(2)
        if st.session_state.page != "saved":
            r1.button("📁 My documents", on_click=go, args=("saved",), key=f"docs_{st.session_state.page}")
        r2.button("← Back to Home", on_click=go, args=("home",), key=f"back_{st.session_state.page}")


def account_bar() -> None:
    if auth.login_required():
        a, b = st.columns([6, 1], vertical_alignment="center")
        a.caption(f"Signed in as **{st.session_state.user}**")
        b.button("Sign out", on_click=sign_out, key=f"signout_{st.session_state.page}")


def page_title(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="le-title">{title}</div><div class="le-divider"><span></span><i></i><span></span></div>'
                f'<div class="le-sub">{subtitle}</div>', unsafe_allow_html=True)


def stepper(active: int) -> None:
    names = ["Details", "Preview", "Edit", "Download"]
    items = "".join(
        f'<div class="le-step {"done" if i < active else "active" if i == active else ""}">'
        f'<b>{"✓" if i < active else i}</b><span>{n}</span></div>' for i, n in enumerate(names, 1))
    st.markdown(f'<div class="le-steps">{items}</div>', unsafe_allow_html=True)


def footer() -> None:
    st.markdown(f'<div class="le-note">{DISCLAIMER}</div>', unsafe_allow_html=True)


def placeholder_banner(text: str) -> None:
    """Warn about [bracketed] / ____ items that still need the user's input."""
    items = du.placeholder_report(text)
    if items:
        total = sum(n for _, n in items)
        listed = ", ".join(f"<code>{label}</code>" + (f" ×{n}" if n > 1 else "") for label, n in items[:6])
        more = f" and {len(items) - 6} more" if len(items) > 6 else ""
        st.markdown(f'<div class="le-warn"><b>⚠ {total} item{"s" if total > 1 else ""} still need your input:</b> '
                    f'{listed}{more}. Use <b>Edit Document</b> to fill them in (the editor has a “Next blank” button).</div>',
                    unsafe_allow_html=True)


MIME_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@st.cache_data(show_spinner=False, max_entries=8)
def _export(text: str, fmt: str) -> bytes:
    """Build each export once per document text (reruns on button clicks stay instant)."""
    return {"txt": du.to_txt, "docx": du.to_docx, "pdf": du.to_pdf}[fmt](text)


def download_buttons(text: str, key: str, cols) -> None:
    """Three real download buttons placed in the given columns; filenames come from the document title."""
    cols[0].download_button("📄 Download as TXT", _export(text, "txt"), du.suggest_filename(text, "txt"), "text/plain", key=f"{key}_txt")
    cols[1].download_button("📘 Download as DOCX", _export(text, "docx"), du.suggest_filename(text, "docx"), MIME_DOCX, key=f"{key}_docx")
    pdf_ok, pdf_why = du.pdf_support(text)
    if pdf_ok:
        cols[2].download_button("📕 Download as PDF", _export(text, "pdf"), du.suggest_filename(text, "pdf"), "application/pdf", key=f"{key}_pdf")
    else:   # e.g. Tamil / Hindi without a shaping engine: a wrong PDF is worse than none
        cols[2].button("📕 PDF unavailable", disabled=True, help=pdf_why, key=f"{key}_pdf_off")


def notices_block(doc_type: str, details: dict) -> None:
    """'Before you sign (India)': stamp paper, registration and other formalities (see ai_core/india_legal.py)."""
    items = india_notices(doc_type, details)
    if not items:
        return
    li = "".join(f'<li>{"⚠" if n.level == "warn" else "ℹ"} <b>{htmllib.escape(n.title)}.</b> {htmllib.escape(n.text)}</li>' for n in items)
    st.markdown(f'<div class="le-legal"><b>⚖ Before you sign (India)</b><ul>{li}</ul>'
                '<small>General information, not legal advice. Rules differ by state and change - confirm with a '
                'local advocate before you sign or register.</small></div>', unsafe_allow_html=True)


def review_block() -> None:
    """Show the last review if it still matches the text on screen. All text is escaped (AI output is untrusted)."""
    ss = st.session_state
    r = ss.review
    if not r or r["for"] != hash(ss.edited_doc):
        return
    esc = htmllib.escape
    if r["issues"]:
        rows = "".join(
            f'<div class="row"><span class="le-pill {i.severity}">{esc(i.severity)}</span><b>{esc(i.title)}</b> '
            f'{"<span class=le-meta>(AI)</span>" if i.source == "ai" else ""}<br>{esc(i.detail)}'
            + (f'<br><span class="le-fix">Fix: {esc(i.suggestion)}</span>' if i.suggestion else "") + "</div>" for i in r["issues"])
        head = f"🔍 Review: {len(r['issues'])} thing(s) to look at"
    else:
        rows, head = '<div class="row">No problems found by the checks that ran.</div>', "🔍 Review"
    how = f"AI review by {esc(r['model'])} + automatic checks" if r["ai"] else "Automatic checks only"
    warn = f'<br><span class="le-meta">{esc(r["warning"])}</span>' if r["warning"] else ""
    st.markdown(f'<div class="le-review"><b>{head}</b> <span class="le-meta">· {how}</span>{warn}{rows}'
                '<div class="le-meta" style="margin-top:.5rem">A review helps you spot gaps; it cannot replace a lawyer.</div></div>',
                unsafe_allow_html=True)


# ---------------------------------------------------------------- pages
ICONS = {  # simple inline SVG icons (navy strokes)
    "doc": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    "sliders": '<path d="M4 7h16M4 12h16M4 17h16"/><circle cx="9" cy="7" r="2" fill="#EAF3FC"/><circle cx="15" cy="12" r="2" fill="#EAF3FC"/><circle cx="8" cy="17" r="2" fill="#EAF3FC"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "bolt": '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
}
FEATURES = [("doc", "Multiple Document Types", "Employment contracts, NDAs, lease agreements and more"),
            ("sliders", "Tailored Questions", "Each document type asks only for the details it needs"),
            ("shield", "Accurate &amp; Reliable", "Based on standard legal structures and formats"),
            ("bolt", "Fast and Easy", "Create your document in just a few steps")]


def page_home() -> None:
    account_bar()
    _, mid, _ = st.columns([1, 2, 1])
    mid.image(str(LOGO), width=520)
    st.markdown('<div class="le-divider"><span></span><i></i><span></span></div>'
                '<div class="le-title">Legal Document Generator</div>'
                '<div class="le-sub">Create customized legal documents with ease</div>'
                '<div class="le-desc">LegalEase leverages AI to help you generate accurate, customizable and professional '
                'legal documents for a variety of use cases. Simply provide the required details and get your document in minutes.</div>',
                unsafe_allow_html=True)
    _, c, _ = st.columns([2, 2, 2])
    c.button("START  →", type="primary", on_click=go, args=("generator",), key="start")
    try:
        has_saved = bool(storage.list_documents(st.session_state.user, 1))
    except Exception:
        has_saved = False
    if has_saved:
        c.button("📁 My documents", on_click=go, args=("saved",), key="my_docs")
    feats = "".join(
        f'<div class="le-feat"><div class="le-ico"><svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#0B2A52" '
        f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{ICONS[i]}</svg></div><h4>{t}</h4><p>{d}</p></div>'
        for i, t, d in FEATURES)
    st.markdown(f'<div class="le-feats">{feats}</div>', unsafe_allow_html=True)
    footer()


def _slug(s: str) -> str:
    return re.sub(r"\W+", "_", s.lower()).strip("_")


def _to_date(iso: str):
    try:
        return date.fromisoformat(iso) if iso else None
    except ValueError:
        return None


def render_field(f, doc_type: str, store: dict, col) -> None:
    """Draw one schema field in `col` and remember its value in `store`.

    Widget state is seeded from `store` (no `value=` argument), so a widget keeps the same identity
    while typing, and values survive switching document types or leaving the page.
    """
    ss = st.session_state
    wkey = f"w_{_slug(doc_type)}_{f.key}"
    label = f.label + (" :red[*]" if f.required else "")
    stored = store.get(f.key, "")
    help_ = f.help or None
    if f.kind == "select":
        opts = [""] + list(f.options)
        if wkey not in ss:
            ss[wkey] = stored if stored in opts else ""
        val = col.selectbox(label, opts, key=wkey, format_func=lambda x: x or "Select…", help=help_)
    elif f.kind == "date":
        if wkey not in ss and _to_date(stored):
            ss[wkey] = _to_date(stored)
        d = col.date_input(label, value=None, key=wkey, format="DD/MM/YYYY", help=help_)
        val = d.isoformat() if d else ""
    elif f.kind == "textarea":
        if wkey not in ss:
            ss[wkey] = stored
        val = col.text_area(label, key=wkey, height=96, placeholder=f.placeholder, help=help_)
    else:
        if wkey not in ss:
            ss[wkey] = stored
        val = col.text_input(label, key=wkey, placeholder=f.placeholder, help=help_)
    store[f.key] = val


def layout_rows(fields):
    """Short fields go two per row; text areas get a full-width row."""
    rows, buf = [], []
    for f in fields:
        if f.kind == "textarea":
            if buf:
                rows.append(buf)
                buf = []
            rows.append([f])
        else:
            buf.append(f)
            if len(buf) == 2:
                rows.append(buf)
                buf = []
    if buf:
        rows.append(buf)
    return rows


def progress_html(done: int, total: int) -> str:
    pct = int(100 * done / total) if total else 100
    full = " full" if done == total else ""
    return (f'<div class="le-prog-label"><span>Required details</span><span><b>{done} of {total}</b> completed</span></div>'
            f'<div class="le-prog{full}"><div style="width:{pct}%"></div></div>')


def page_generator() -> None:
    ss = st.session_state
    header()
    stepper(1)
    page_title("Legal Document Generator", "Choose a document type, then fill in the details it needs")

    if "w_doc_type" not in ss:
        ss["w_doc_type"] = ss.doc_type or ""
    if "w_eff_date" not in ss:
        ss["w_eff_date"] = ss.eff_date or date.today()

    with st.container(key="gen_card"):
        if "w_language" not in ss:
            ss["w_language"] = ss.language if ss.language in LANGUAGES else "English"
        c1, c2, c3 = st.columns([3, 2, 2])
        doc_type = c1.selectbox("Document Type :red[*]", [""] + DOCUMENT_TYPES, key="w_doc_type",
                                format_func=lambda x: x or "Select a document type")
        eff = c2.date_input("Effective Date :red[*]", key="w_eff_date", format="DD/MM/YYYY")
        language = c3.selectbox("Language", list(LANGUAGES), key="w_language", format_func=lambda x: LANGUAGES[x],
                                help="Tamil and Hindi drafts are written by Gemini (an API key is required).")
        ss.doc_type, ss.eff_date, ss.language = doc_type or None, eff, language
        if language != "English":
            st.markdown('<div class="le-typedesc">Tamil / Hindi drafts should be read by a fluent speaker or a lawyer before '
                        'signing. For PDF export see the README (the DOCX download always works).</div>', unsafe_allow_html=True)

        if not doc_type:
            st.markdown('<div class="le-hint">👆 Select a document type to see the details we need.<br>'
                        'Each type asks different questions - for example rent and deposit for a lease, '
                        'or salary and notice period for an employment contract.</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="le-typedesc">{DESCRIPTIONS[doc_type]}</div>', unsafe_allow_html=True)
            fields = get_fields(doc_type)
            store = ss.form_values.setdefault(doc_type, {})
            for group in GROUP_ORDER:
                gf = [f for f in fields if f.group == group]
                if not gf:
                    continue
                st.markdown(f'<div class="le-sec"><i></i>{group}</div>', unsafe_allow_html=True)
                for row in layout_rows(gf):
                    for f, col in zip(row, st.columns(len(row)) if len(row) > 1 else [st.container()]):
                        render_field(f, doc_type, store, col)

            required = [f for f in fields if f.required]
            done = sum(1 for f in required if str(store.get(f.key, "")).strip())
            st.markdown(progress_html(done, len(required)), unsafe_allow_html=True)
            _, c, _ = st.columns([1, 2, 1])
            clicked = c.button("GENERATE DOCUMENT  →", type="primary", key="gen_btn")
            if daily_limit("generate"):
                try:
                    left = max(0, daily_limit("generate") - usage_today(ss.user))
                    c.caption(f"AI drafts left today: {left} of {daily_limit('generate')}")
                except Exception:
                    pass

            if clicked:
                missing = missing_required(doc_type, store)
                if missing:
                    st.error("Please fill in the required field(s): " + ", ".join(missing))
                else:
                    details = {k: v.strip() for k, v in store.items() if str(v).strip()}
                    try:
                        with st.spinner("Drafting your legal document… AI drafting can take up to a minute."):
                            res = request_document(doc_type, details, eff, language, ss.user)
                    except (RateLimitExceeded, GenerationRefused, ValueError) as exc:
                        st.error(str(exc))
                    else:
                        ss.original_doc = ss.edited_doc = res.text
                        ss.source, ss.model, ss.warning = res.source, res.model, res.warning
                        ss.notice_details, ss.doc_id, ss.review = dict(details), None, None
                        ss.language = language if res.source == "gemini" else "English"   # the offline template is English
                        persist()
                        ss.page = "preview"
                        st.rerun()
    footer()


def page_preview(final: bool = False) -> None:
    ss = st.session_state
    header()
    stepper(4 if final else 2)
    if final:
        page_title("Your Document is Ready", "Your changes have been saved. Download the final document below.")
    else:
        page_title("Legal Document Preview", "Review your generated legal document before editing or downloading.")
    _, mid, _ = st.columns([1, 6, 1])
    with mid:
        if final:
            st.markdown('<div class="le-ok"><b>✔</b>Changes saved successfully!</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="le-ok"><b>✔</b>Document generated successfully!</div>', unsafe_allow_html=True)
            if ss.source == "template":
                reason = ss.warning or "No GEMINI_API_KEY is set in your .env file, so the built-in template was used."
                st.markdown(f'<div class="le-warn"><b>Built-in template used.</b> {reason}</div>', unsafe_allow_html=True)

        chips = [ss.doc_type or "Legal document", f"Effective {ss.eff_date.strftime('%d %b %Y')}" if ss.eff_date else "",
                 f"{len(ss.edited_doc.split()):,} words", ss.language if ss.language != "English" else ""]
        html = "".join(f'<span class="le-chip">{c}</span>' for c in chips if c)
        if ss.model:
            html += f'<span class="le-chip">✨ {ss.model}</span>'
        elif ss.source == "template":
            html += '<span class="le-chip gold">Built-in template</span>'
        else:
            html += '<span class="le-chip">Saved draft</span>'
        st.markdown(f'<div class="le-chips">{html}</div>', unsafe_allow_html=True)

        notices_block(ss.doc_type or "", ss.notice_details)
        placeholder_banner(ss.edited_doc)
        review_block()
        st.markdown(du.render_html(ss.edited_doc), unsafe_allow_html=True)
        st.caption("ⓘ You can edit the generated document before downloading." if not final else "ⓘ You can still edit the document again.")
        if ss.save_error:
            st.caption(f"⚠ {ss.save_error}")
        elif ss.doc_id:
            st.caption("💾 Saved in My documents - you can reopen it later.")
        cols = st.columns(4)
        cols[0].button("✏️ Edit Document  →", type="primary", on_click=go, args=("edit",), key="edit_btn")
        download_buttons(ss.edited_doc, "p", cols[1:])
        rv, _ = st.columns([1.4, 3])
        rv.button("🔍 Review for risks", on_click=run_review, key="review_btn",
                  help="Looks for missing or vague clauses (termination, liability, jurisdiction...).")
        with st.container(key="link_row"):
            l1, l2, _ = st.columns([1, 1, 2])
            l1.button("← Change details", on_click=go, args=("generator",), key="change_details")
            l2.button("＋ New document", on_click=new_document, key="new_doc")
    footer()


def page_edit() -> None:
    ss = st.session_state
    header()
    stepper(3)
    page_title("Edit Document", "Make changes to your document content. The preview updates in real-time as you type.")

    # Sticky action bar: Save / Cancel stay on screen however long the document is.
    with st.container(key="editbar"):
        c_state, c_cancel, c_save = st.columns([3, 1.3, 1.8], vertical_alignment="center")
        state = c_state.empty()
        c_cancel.button("✕ Cancel", on_click=go, args=("preview",), key="cancel")
        c_save.button("💾 Save Changes", type="primary", on_click=save_changes, key="save")

    if ss.edit_error:
        st.error("The document is empty. Add some text, or press Cancel to keep the previous version.")

    live = EDITOR(text=ss.editor_text, original=ss.original_doc, token=ss.editor_token, key="editor", default=None)
    if isinstance(live, dict) and live.get("token") == ss.editor_token and "text" in live:  # ignore stale sessions
        ss.editor_text = live["text"]
        nonce = live.get("save")
        if nonce and nonce != ss.last_save_nonce:  # "Save & continue" / Ctrl+S inside the editor
            ss.last_save_nonce = nonce
            commit_edit(live["text"])
            st.rerun()

    dirty = ss.editor_text != ss.edited_doc
    state.markdown('<div class="le-state dirty"><i></i>Unsaved changes</div>' if dirty
                   else '<div class="le-state clean"><i></i>All changes saved</div>', unsafe_allow_html=True)
    st.caption("Cancel discards your edits since you opened the editor. Save Changes (or Ctrl+S in the editor) keeps them "
               "and opens the download page.")
    footer()


def page_saved() -> None:
    ss = st.session_state
    header()
    account_bar()
    page_title("My Documents", "Reopen, keep editing or delete your earlier drafts")
    try:
        docs = storage.list_documents(ss.user)
    except Exception as exc:
        st.error(f"Could not read your saved documents ({type(exc).__name__}).")
        docs = []
    if not docs:
        st.markdown('<div class="le-hint">No saved documents yet.<br>Every document you generate is saved here automatically.</div>',
                    unsafe_allow_html=True)
    for d in docs:
        with st.container(key=f"doc_{d.id}"):
            c1, c2, c3 = st.columns([6, 1.4, 1.6], vertical_alignment="center")
            c1.markdown(f"**{htmllib.escape(d.title)}**  \n:gray[{d.doc_type} · {d.language} · updated {d.updated_at[:10]}]")
            c2.button("Open", on_click=open_saved, args=(d.id,), key=f"open_{d.id}")
            confirm = ss.confirm_delete == d.id
            c3.button("Confirm delete" if confirm else "Delete", on_click=delete_saved, args=(d.id,),
                      type="primary" if confirm else "secondary", key=f"del_{d.id}")
    footer()


# ---------------------------------------------------------------- router
load_css()
require_login()
PAGES = {"home": page_home, "generator": page_generator, "preview": page_preview,
         "edit": page_edit, "final": lambda: page_preview(final=True), "saved": page_saved}
if st.session_state.page in ("preview", "edit", "final") and not st.session_state.edited_doc:
    st.session_state.page = "generator"  # no document yet -> send user to the form
PAGES[st.session_state.page]()
