"""Headless UI tests using Streamlit's AppTest (the custom editor component is not rendered there)."""
import sys
from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "frontend"))
sys.path.insert(0, str(ROOT))
APP = str(ROOT / "frontend" / "app.py")


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")           # force the offline template; never call the network in tests


def fresh() -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    return at


def labels(at):
    return [w.label for w in list(at.text_input) + list(at.text_area) + list(at.selectbox) + list(at.date_input)]


def button(at, key):
    return next(b for b in at.button if b.key == key)


def test_home_to_generator_shows_hint_only():
    at = fresh()
    assert not at.exception
    button(at, "start").click().run()
    assert at.session_state.page == "generator"
    assert any("Select a document type" in m.value for m in at.markdown)   # the hint card
    assert [s.label for s in at.selectbox][0].startswith("Document Type")
    assert len(at.text_input) == 0                       # nothing until a type is chosen


@pytest.mark.parametrize("doc_type,expect", [
    ("Lease Agreement", ["Monthly rent", "Security deposit", "Landlord name", "Tenant name"]),
    ("Employment Contract", ["Job title", "Salary / compensation", "Employer name", "Employee name"]),
    ("Non-Disclosure Agreement", ["Purpose of disclosure", "Confidentiality duration", "Disclosing Party name"]),
    ("Freelance Work Contract", ["Project description", "Total fee", "Delivery deadline"]),
])
def test_fields_depend_on_document_type(doc_type, expect):
    at = fresh()
    button(at, "start").click().run()
    at.selectbox(key="w_doc_type").select(doc_type).run()
    assert not at.exception
    shown = " | ".join(labels(at))
    for e in expect:
        assert e in shown, (e, shown)
    # fields of another type must not leak in
    other = "Monthly rent" if doc_type != "Lease Agreement" else "Salary / compensation"
    assert other not in shown


def test_switching_type_changes_fields_and_keeps_values():
    at = fresh()
    button(at, "start").click().run()
    at.selectbox(key="w_doc_type").select("Lease Agreement").run()
    at.text_input(key="w_lease_agreement_monthly_rent").set_value("₹25,000").run()
    at.selectbox(key="w_doc_type").select("Service Agreement").run()
    assert "Monthly rent" not in " ".join(labels(at))
    at.selectbox(key="w_doc_type").select("Lease Agreement").run()
    assert at.text_input(key="w_lease_agreement_monthly_rent").value == "₹25,000"


def test_validation_lists_missing_required_fields():
    at = fresh()
    button(at, "start").click().run()
    at.selectbox(key="w_doc_type").select("Offer Letter").run()
    button(at, "gen_btn").click().run()
    assert at.session_state.page == "generator"
    assert at.error and "Joining date" in at.error[0].value and "Candidate name" in at.error[0].value


def fill_lease(at):
    vals = {"party1_name": "Asha Rao", "party2_name": "Ravi Kumar", "monthly_rent": "₹25,000",
            "security_deposit": "₹1,00,000", "lease_term": "11 months"}
    for k, v in vals.items():
        at.text_input(key=f"w_lease_agreement_{k}").set_value(v)
    at.text_area(key="w_lease_agreement_property_address").set_value("12 Main Road")
    at.selectbox(key="w_lease_agreement_property_type").select("Residential")
    at.run()


def test_full_flow_generate_edit_save():
    at = fresh()
    button(at, "start").click().run()
    at.selectbox(key="w_doc_type").select("Lease Agreement").run()
    fill_lease(at)
    assert not at.exception
    button(at, "gen_btn").click().run()
    assert at.session_state.page == "preview", [e.value for e in at.error]
    doc = at.session_state.edited_doc
    assert "Asha Rao" in doc and "₹25,000" in doc and "Landlord" in doc
    assert not [w for w in at.warning]                   # no Streamlit widget warnings anywhere

    button(at, "edit_btn").click().run()
    assert at.session_state.page == "edit" and not at.exception
    assert {b.key for b in at.button} >= {"cancel", "save"}   # Save is present on the edit page
    token = at.session_state.editor_token

    # Save with a live value from the CURRENT session
    at.session_state["editor"] = {"text": doc + "\nEXTRA LINE", "token": token}
    button(at, "save").click().run()
    assert at.session_state.page == "final"
    assert at.session_state.edited_doc.endswith("EXTRA LINE")


def test_stale_editor_value_from_old_session_is_ignored():
    at = fresh()
    button(at, "start").click().run()
    at.selectbox(key="w_doc_type").select("Lease Agreement").run()
    fill_lease(at)
    button(at, "gen_btn").click().run()
    original = at.session_state.edited_doc
    button(at, "edit_btn").click().run()
    old_token = at.session_state.editor_token
    at.session_state["editor"] = {"text": "DISCARDED EDITS", "token": old_token}
    button(at, "cancel").click().run()
    button(at, "edit_btn").click().run()                  # re-open: new token, old component value still around
    assert at.session_state.editor_token == old_token + 1
    button(at, "save").click().run()                      # save immediately without typing
    assert at.session_state.edited_doc == original        # NOT "DISCARDED EDITS"


def test_empty_document_is_never_saved():
    at = fresh()
    button(at, "start").click().run()
    at.selectbox(key="w_doc_type").select("Lease Agreement").run()
    fill_lease(at)
    button(at, "gen_btn").click().run()
    original = at.session_state.edited_doc
    button(at, "edit_btn").click().run()
    at.session_state["editor"] = {"text": "   ", "token": at.session_state.editor_token}
    button(at, "save").click().run()
    assert at.session_state.page == "edit" and at.session_state.edited_doc == original
    assert at.error and "empty" in at.error[0].value


def test_new_document_clears_form():
    at = fresh()
    button(at, "start").click().run()
    at.selectbox(key="w_doc_type").select("Lease Agreement").run()
    fill_lease(at)
    button(at, "gen_btn").click().run()
    button(at, "new_doc").click().run()
    assert at.session_state.page == "generator" and at.session_state.edited_doc == ""
    assert at.selectbox(key="w_doc_type").value == ""
