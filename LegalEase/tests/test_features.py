"""Tests for: Indian-law notices, review, Tamil/Hindi support, saved drafts, login and cost limits."""
import io
import re
import zipfile
from datetime import date

import pytest

import auth
from ai_core import generate_document, get_fields, storage
from ai_core import gemini_generator as gg
from ai_core.india_legal import notices, parse_term_months
from ai_core.limits import RateLimitExceeded, burst, check_and_consume, check_input_size, usage_today
from ai_core.review import _parse_ai_issues, check_document, review_document
from exporters import document_utils as du

EFF = date(2026, 10, 1)


def lease_details(**kw):
    d = {f.key: (f.options[0] if f.options else "value") for f in get_fields("Lease Agreement") if f.required}
    return d | {"party1_name": "Asha Rao", "party2_name": "Ravi Kumar"} | kw


def template(doc_type="Lease Agreement", **kw):
    d = {f.key: (f.options[0] if f.options else "value") for f in get_fields(doc_type) if f.required}
    return generate_document(doc_type, d | {"party1_name": "A", "party2_name": "B"} | kw, EFF).text


# ---------------------------------------------------------------- Indian formalities
@pytest.mark.parametrize("text,months", [("11 months", 11), ("1 year", 12), ("2 years", 24), ("eleven months", 11),
                                         ("3 years 6 months", 42), ("36-month", 36), ("", None), ("soon", None)])
def test_parse_term_months(text, months):
    assert parse_term_months(text) == months


def test_lease_over_a_year_must_be_registered_and_short_lease_is_info():
    long = {n.title: n for n in notices("Lease Agreement", {"lease_term": "3 years"})}
    short = {n.title: n for n in notices("Lease Agreement", {"lease_term": "11 months"})}
    assert long["This lease must be registered"].level == "warn"
    assert "This lease must be registered" not in short and short["Lease registration"].level == "info"


def test_every_document_gets_stamp_paper_notice_first_and_nda_has_no_extras():
    assert notices("Non-Disclosure Agreement")[0].title == "Stamp paper"
    assert [n.title for n in notices("Partnership Agreement")][:2] == ["Stamp paper", "Register the firm"]


def test_non_compete_warning_only_when_asked_for():
    assert not any("Non-compete" in n.title for n in notices("Employment Contract", {"additional_terms": "pay on time"}))
    assert any("Non-compete" in n.title for n in notices("Employment Contract", {"additional_terms": "No non-compete for 2 years"}))


# ---------------------------------------------------------------- review
def test_review_flags_missing_clauses_in_a_thin_document():
    titles = {i.title for i in check_document("Service Agreement", "SERVICE AGREEMENT\n1. FEES\n1.1 Pay [Amount] when asked.")}
    assert {"No termination clause", "No liability limit or indemnity", "No dispute resolution", "No governing law"} <= titles
    assert any("unfilled placeholder" in t for t in titles)


def test_review_flags_vague_wording_in_the_builtin_template():
    # Real finding: the offline template says "as agreed between the Parties" instead of using the user's numbers.
    assert "Vague wording" in {i.title for i in check_document("Lease Agreement", template())}


def test_signature_blanks_are_not_reported_as_placeholders():
    text = "X\nY\n1. TERMINATION\n1.1 Either party may terminate. Governed by the laws of India. Disputes go to courts. Witness below.\nSignature: ______\nName: ______"
    assert not any("placeholder" in i.title for i in check_document("Non-Disclosure Agreement", text))


def test_review_without_key_uses_rules_only_and_never_raises():
    r = review_document("Lease Agreement", template(), key="")
    assert r.issues and not r.ai_used
    r = review_document("Lease Agreement", template(), key="", language="Tamil")
    assert not r.issues and "English" in r.warning


def test_ai_review_is_merged_and_ai_failure_degrades_gracefully(monkeypatch):
    body = {"candidates": [{"content": {"parts": [{"text": '[{"severity":"HIGH","title":"Dates contradict","detail":"d","suggestion":"s"}]'}]}}]}

    class R:
        status_code, reason, text = 200, "", ""
        json = lambda self: body

    monkeypatch.setattr(gg.requests, "post", lambda *a, **k: R())
    r = review_document("Lease Agreement", template(), key="k")
    assert r.ai_used and r.model and any(i.source == "ai" and i.severity == "high" for i in r.issues)

    class Bad(R):
        status_code = 429
        json = lambda self: {"error": {"message": "quota"}}

    monkeypatch.setattr(gg.requests, "post", lambda *a, **k: Bad())
    monkeypatch.setattr(gg.time, "sleep", lambda s: None)
    r = review_document("Lease Agreement", template(), key="k")
    assert not r.ai_used and r.issues and "unavailable" in r.warning


def test_parse_ai_issues_tolerates_fences_and_junk():
    out = _parse_ai_issues('```json\n[{"severity":"nonsense","title":"T","detail":"d"},{"x":1},"str"]\n```')
    assert [(i.severity, i.title) for i in out] == [("medium", "T")]


# ---------------------------------------------------------------- Tamil / Hindi
TAMIL = ("# குத்தகை ஒப்பந்தம்\nநடைமுறை தேதி: 1 அக்டோபர் 2026\n\n# பின்னணி\nA. அறிமுகம் உரை.\n\n3. வாடகை\n"
         "3.1 வாடகை மாதம் ₹25,000 ஆகும்.\n- **முக்கியம்** புள்ளி\nகையொப்பம்: ______________\n1. பெயர்: ____  கையொப்பம்: ____")


def kinds(text):
    return [(k, t) for k, t in du.parse_document(text) if k != "gap"]


def test_uncased_scripts_get_headings_clauses_and_signature_lines():
    got = kinds(TAMIL)
    assert got[0][0] == "title" and got[1][0] == "subtitle"
    assert ("heading", "பின்னணி") in got and ("heading", "3. வாடகை") in got
    assert ("clause", "A. அறிமுகம் உரை.") in got and ("clause", "3.1 வாடகை மாதம் ₹25,000 ஆகும்.") in got
    assert du.find_placeholders(TAMIL) == []          # pen blanks are intentional


def test_english_parsing_is_unchanged():
    got = kinds("LEASE\nEffective Date: X\n1. DEFINITIONS\n1.1 Hello.\n2. The Employee shall work.\nA. The Parties wish.\nSIGNATURES")
    assert [k for k, _ in got] == ["title", "subtitle", "heading", "clause", "para", "clause", "heading"]


def test_docx_marks_indian_script_runs_as_complex_script():
    xml = zipfile.ZipFile(io.BytesIO(du.to_docx(TAMIL))).read("word/document.xml").decode()
    assert "<w:cs/>" in xml and "<w:bCs/>" in xml
    assert re.search(r"<w:rPr><w:b/><w:bCs/>.*?<w:cs/></w:rPr>", xml)            # schema order: b, bCs ... cs


def test_pdf_support_is_honest_about_indian_scripts(monkeypatch):
    monkeypatch.setattr(du, "_weasyprint_ok", lambda: False)
    ok, why = du.pdf_support(TAMIL)
    assert not ok and "DOCX" in why
    with pytest.raises(RuntimeError):
        du.to_pdf(TAMIL)
    assert du.pdf_support("plain English")[0] and du.to_pdf("T\nS\n1. A\n1.1 x ₹5").startswith(b"%PDF")


def test_tamil_prompt_and_completeness_check(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    sent = {}
    doc = "# குத்தகை ஒப்பந்தம்\n" + "\n".join(f"{i}.1 " + "சொல் " * 60 for i in range(1, 8)) + "\nகையொப்பம்: ______________"

    class R:
        status_code, reason, text = 200, "", ""
        json = lambda self: {"candidates": [{"content": {"parts": [{"text": doc}]}, "finishReason": "STOP"}]}

    def fake(url, json=None, **kw):
        sent["prompt"] = json["contents"][0]["parts"][0]["text"]
        return R()

    monkeypatch.setattr(gg.requests, "post", fake)
    r = generate_document("Lease Agreement", lease_details(), EFF, language="Tamil")
    assert r.source == "gemini" and "Tamil" in sent["prompt"] and r.text.startswith("# குத்தகை")
    assert "LANGUAGE:" not in gg._build_prompt("Lease Agreement", {"party1_name": "A"}, EFF)   # English prompt unchanged


def test_tamil_without_key_falls_back_to_english_template_with_explanation(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    r = generate_document("Lease Agreement", lease_details(), EFF, language="Hindi")
    assert r.source == "template" and "Hindi drafting needs Gemini" in r.warning
    with pytest.raises(ValueError):
        generate_document("Lease Agreement", lease_details(), EFF, language="Klingon")


# ---------------------------------------------------------------- saved drafts
def test_save_list_update_open_delete_roundtrip():
    i = storage.save_document("alice", "Lease Agreement", "LEASE\nbody", {"party1_name": "Asha", "party2_name": "Ravi"}, "English", "2026-10-01")
    d = storage.get_document("alice", i)
    assert d.title == "Lease Agreement - Asha & Ravi" and d.details["party1_name"] == "Asha" and d.effective_date == "2026-10-01"
    assert storage.save_document("alice", "Lease Agreement", "LEASE\nedited", {}, doc_id=i) == i
    assert storage.get_document("alice", i).text.endswith("edited") and len(storage.list_documents("alice")) == 1
    assert storage.delete_document("alice", i) and storage.list_documents("alice") == []


def test_users_cannot_see_update_or_delete_each_others_documents():
    i = storage.save_document("alice", "NDA", "secret")
    assert storage.get_document("bob", i) is None and storage.list_documents("bob") == []
    assert not storage.delete_document("bob", i)
    j = storage.save_document("bob", "NDA", "bobs", doc_id=i)           # id belongs to alice -> must insert, not overwrite
    assert j != i and storage.get_document("alice", i).text == "secret"


def test_tamil_text_and_empty_documents():
    i = storage.save_document("a", "Lease Agreement", TAMIL, language="Tamil")
    assert storage.get_document("a", i).text == TAMIL and storage.get_document("a", i).language == "Tamil"
    with pytest.raises(ValueError):
        storage.save_document("a", "Lease Agreement", "   ")


# ---------------------------------------------------------------- login
def test_password_hashing_and_user_login(monkeypatch):
    h = auth.hash_password("s3cret!")
    assert auth.verify_password("s3cret!", h) and not auth.verify_password("wrong", h) and not auth.verify_password("x", "junk")
    assert h != auth.hash_password("s3cret!")                                   # salted
    assert not auth.login_required() and auth.api_user(None) == "local"       # open dev mode
    monkeypatch.setenv("LEGALEASE_USERS", f"alice={h}")
    assert auth.login_required() and auth.authenticate("alice", "s3cret!")
    assert not auth.authenticate("alice", "bad") and not auth.authenticate("eve", "s3cret!")


def test_api_keys(monkeypatch):
    monkeypatch.setenv("LEGALEASE_API_KEYS", "k-123=alice,k-456=bob")
    assert auth.api_user("k-456") == "bob"
    for bad in (None, "", "k-12", "k-1234"):
        with pytest.raises(PermissionError):
            auth.api_user(bad)
    monkeypatch.delenv("LEGALEASE_API_KEYS")
    monkeypatch.setenv("LEGALEASE_REQUIRE_LOGIN", "1")                          # login required but no keys: fail closed
    with pytest.raises(PermissionError):
        auth.api_user("anything")


# ---------------------------------------------------------------- cost limits
def test_daily_quota_per_user_and_global_cap(monkeypatch):
    monkeypatch.setenv("LEGALEASE_DAILY_LIMIT", "2")
    check_and_consume("alice")
    check_and_consume("alice")
    with pytest.raises(RateLimitExceeded) as e:
        check_and_consume("alice")
    assert "limit of 2" in str(e.value) and "documents" in str(e.value) and e.value.retry_after > 0 and usage_today("alice") == 2
    check_and_consume("bob")                                                    # another user is unaffected
    monkeypatch.setenv("LEGALEASE_GLOBAL_DAILY_LIMIT", "2")                     # alice 2 + bob 1 already used... cap is 2 more
    with pytest.raises(RateLimitExceeded) as e:
        check_and_consume("carol")
    assert "capacity" in str(e.value)


def test_quota_survives_a_restart_and_reviews_are_counted_separately(monkeypatch):
    monkeypatch.setenv("LEGALEASE_DAILY_LIMIT", "1")
    check_and_consume("a")
    burst.reset()                                                               # simulates a new process: memory gone, DB stays
    with pytest.raises(RateLimitExceeded):
        check_and_consume("a")
    check_and_consume("a", "review")


def test_burst_limit(monkeypatch):
    monkeypatch.setenv("LEGALEASE_BURST_LIMIT", "2")
    check_and_consume("a")
    check_and_consume("a")
    with pytest.raises(RateLimitExceeded) as e:
        check_and_consume("a")
    assert "wait" in str(e.value)


def test_oversized_input_is_rejected_before_it_costs_money():
    check_input_size({"a": "x" * 100})
    with pytest.raises(ValueError):
        check_input_size({"a": "x" * 5000})
    with pytest.raises(ValueError):
        check_input_size({str(i): "x" * 3000 for i in range(8)})
