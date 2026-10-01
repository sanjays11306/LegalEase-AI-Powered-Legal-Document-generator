"""Backend tests: schemas, template output and the Gemini model chain (network is mocked)."""
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_core import DOCUMENT_TYPES, configured_models, generate_document, get_fields, missing_required  # noqa: E402
from ai_core import gemini_generator as gg  # noqa: E402

EFF = date(2026, 10, 1)
GOOD = ("TITLE\nEffective Date: October 1, 2026\n\n1. HEADING\n" + "\n".join(f"1.{i} " + "word " * 40 for i in range(1, 12))
        + "\n\nSIGNATURES\nSignature: ____")


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body, self.reason, self.text = status, body or {}, "x", ""

    def json(self):
        return self._body


def ok_body(text=GOOD):
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}


def err_body(msg):
    return {"error": {"message": msg}}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for k in ("GEMINI_MODEL", "GEMINI_FALLBACK_MODELS", "GEMINI_THINKING_LEVEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gg.time, "sleep", lambda s: None)


def details(doc_type):
    return {f.key: ("2026-11-01" if f.kind == "date" else f.options[0] if f.options else "value")
            for f in get_fields(doc_type) if f.required}


# ---------------------------------------------------------------- schemas / template
@pytest.mark.parametrize("doc_type", DOCUMENT_TYPES)
def test_every_type_has_parties_and_required_fields(doc_type):
    keys = [f.key for f in get_fields(doc_type)]
    assert len(keys) == len(set(keys))
    assert {"party1_name", "party2_name", "governing_law", "additional_terms"} <= set(keys)
    assert missing_required(doc_type, {}) and not missing_required(doc_type, details(doc_type))


@pytest.mark.parametrize("doc_type", DOCUMENT_TYPES)
def test_template_uses_the_supplied_details(doc_type, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    d = details(doc_type) | {"party1_name": "Asha Rao", "party2_name": "Ravi Kumar", "party1_address": "1 Lake View",
                             "governing_law": "India; courts at Pune", "additional_terms": "no pets; pay on time"}
    r = generate_document(doc_type, d, EFF)
    assert r.source == "template" and r.model == ""
    for needle in ("Asha Rao", "Ravi Kumar", "1 Lake View", "courts at Pune", "No pets.", "Pay on time."):
        assert needle in r.text, needle
    assert "[Jurisdiction]" not in r.text and "KEY TERMS" in r.text


def test_legacy_parties_and_terms_still_work(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    r = generate_document("Service Agreement", {}, EFF, parties="ABC Company and John Doe", terms="Payment within 30 days")
    assert "ABC Company" in r.text and "John Doe" in r.text and "Payment within 30 days." in r.text


# ---------------------------------------------------------------- Gemini model chain
def test_default_model_is_latest_and_chain_is_deduplicated(monkeypatch):
    assert configured_models()[0] == "gemini-3.8-flash"
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.7-flash")
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "gemini-3.1-pro-preview, gemini-3.7-flash")
    assert configured_models() == ["gemini-3.7-flash", "gemini-3.1-pro-preview", "gemini-3.8-flash", "gemini-3.6-flash"]


def test_request_payload_has_no_deprecated_sampling_params(monkeypatch):
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, body=json, headers=headers)
        return FakeResp(200, ok_body())

    monkeypatch.setattr(gg.requests, "post", fake_post)
    r = generate_document("Lease Agreement", details("Lease Agreement"), EFF)
    assert r.source == "gemini" and r.model == "gemini-3.8-flash" and r.warning == ""
    assert "gemini-3.8-flash:generateContent" in sent["url"]
    cfg = sent["body"]["generationConfig"]
    assert not {"temperature", "topP", "topK", "candidateCount"} & set(cfg)
    assert cfg["thinkingConfig"] == {"thinkingLevel": "medium"}
    assert sent["body"]["systemInstruction"] and sent["headers"]["x-goog-api-key"] == "test-key"
    prompt = sent["body"]["contents"][0]["parts"][0]["text"]
    assert "value" in prompt and "Lease Agreement" in prompt


def test_falls_back_to_next_model_when_first_is_unavailable(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append(url.split("models/")[1].split(":")[0])
        if "3.8" in url:
            return FakeResp(404, err_body("model not found"))
        return FakeResp(200, ok_body())

    monkeypatch.setattr(gg.requests, "post", fake_post)
    r = generate_document("Offer Letter", details("Offer Letter"), EFF)
    assert r.source == "gemini" and r.model == "gemini-3.7-flash" and calls == ["gemini-3.8-flash", "gemini-3.7-flash"]


def test_old_env_model_that_is_restricted_still_works(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")      # what the old .env.example told people to use

    def fake_post(url, **kw):
        return FakeResp(403, err_body("restricted")) if "2.5" in url else FakeResp(200, ok_body())

    monkeypatch.setattr(gg.requests, "post", fake_post)
    assert generate_document("Offer Letter", details("Offer Letter"), EFF).model == "gemini-3.8-flash"


def test_retries_without_thinking_config_if_model_rejects_it(monkeypatch):
    bodies = []

    def fake_post(url, json=None, **kw):
        bodies.append(json["generationConfig"].copy())
        if "thinkingConfig" in json["generationConfig"]:
            return FakeResp(400, err_body("Thinking level is not supported"))
        return FakeResp(200, ok_body())

    monkeypatch.setattr(gg.requests, "post", fake_post)
    assert generate_document("Lease Agreement", details("Lease Agreement"), EFF).source == "gemini"
    assert "thinkingConfig" in bodies[0] and "thinkingConfig" not in bodies[1]


def test_bad_api_key_stops_immediately_with_clear_warning(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        return FakeResp(400, err_body("API key not valid. Please pass a valid API key."))

    monkeypatch.setattr(gg.requests, "post", fake_post)
    r = generate_document("Lease Agreement", details("Lease Agreement"), EFF)
    assert len(calls) == 1 and r.source == "template" and "GEMINI_API_KEY" in r.warning


def test_all_models_failing_returns_template_with_reason(monkeypatch):
    monkeypatch.setattr(gg.requests, "post", lambda url, **kw: FakeResp(429, err_body("quota exceeded")))
    r = generate_document("Lease Agreement", details("Lease Agreement"), EFF)
    assert r.source == "template" and "quota" in r.warning.lower() and r.text.startswith("LEASE AGREEMENT")


def test_incomplete_draft_is_rejected(monkeypatch):
    monkeypatch.setattr(gg.requests, "post", lambda url, **kw: FakeResp(200, ok_body("too short")))
    r = generate_document("Lease Agreement", details("Lease Agreement"), EFF)
    assert r.source == "template" and "incomplete" in r.warning
