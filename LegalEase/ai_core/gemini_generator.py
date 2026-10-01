"""Document generation logic (no UI code here).

generate_document() asks Gemini when GEMINI_API_KEY is set in .env and falls back to a detailed
built-in template if the key is missing or every model fails.  The result says which one was used
and, if the AI could not be reached, why (so the UI can tell the user instead of failing silently).

Gemini notes (checked against the Gemini API docs, Oct 2026):
  * Default model is gemini-3.8-flash (GA).  gemini-3.7-flash / 3.6-flash are tried next.
  * `temperature`, `top_p`, `top_k` are deprecated for current models, so they are NOT sent.
  * Reasoning is controlled with thinkingConfig.thinkingLevel (low | medium | high).
"""
import os
import re
import time
from datetime import date
from typing import NamedTuple

import requests
from dotenv import load_dotenv

from .document_schemas import (DOCUMENT_TYPES, GROUP_ORDER, ROLES, field_map, get_fields,  # noqa: F401
                               missing_required, pretty_value)

load_dotenv()

# Recital A for each document type
PURPOSE = {
    "Employment Contract": "The {a} wishes to employ the {b}, and the {b} wishes to accept employment with the {a}, on the terms set out in this Agreement.",
    "Freelance Work Contract": "The {b} wishes to engage the {a} as an independent contractor to perform certain services, and the {a} has agreed to provide them on the terms set out in this Agreement.",
    "Lease Agreement": "The {a} is entitled to let the premises described in this Agreement, and the {b} wishes to take the premises on lease on the terms set out in this Agreement.",
    "Non-Disclosure Agreement": "The Parties wish to explore a business relationship and, in doing so, the {a} will disclose certain confidential information to the {b}.",
    "Service Agreement": "The {a} carries on the business of providing services, and the {b} wishes to engage the {a} to provide such services on the terms set out in this Agreement.",
    "Partnership Agreement": "The {a} and the {b} wish to carry on business together as partners and to record the terms of their partnership.",
    "Offer Letter": "The {a} is pleased to offer employment to the {b}, and this Agreement records the terms of that offer.",
}

# Type-specific sections: (HEADING, [sub-clauses]).  {a}/{b} become the party roles.
CLAUSES = {
    "Employment Contract": [
        ("APPOINTMENT AND DUTIES", [
            "The {a} hereby appoints the {b}, and the {b} accepts such appointment, with effect from the Effective Date.",
            "The {b} shall perform all duties assigned by the {a} diligently, honestly and to the best of the {b}'s ability, and shall comply with all lawful instructions and workplace policies.",
            "The {b} shall not, without the prior written consent of the {a}, engage in any other employment or business that conflicts with the {a}'s interests."]),
        ("REMUNERATION AND BENEFITS", [
            "The {a} shall pay the {b} the salary agreed between the Parties in writing, subject to deduction of applicable taxes and statutory contributions.",
            "The {b} shall be entitled to leave and other benefits in accordance with the {a}'s policies and applicable law.",
            "The {a} shall reimburse reasonable business expenses incurred by the {b} with prior approval and supported by receipts."]),
        ("CONFIDENTIALITY AND INTELLECTUAL PROPERTY", [
            "The {b} shall keep confidential all non-public information of the {a} during and after employment.",
            "All work product, inventions and materials created by the {b} in the course of employment shall be the exclusive property of the {a}."]),
        ("TERM AND TERMINATION", [
            "This Agreement shall continue until terminated by either Party by giving written notice as agreed between the Parties.",
            "The {a} may terminate this Agreement immediately in the event of serious misconduct, material breach or dishonesty by the {b}.",
            "On termination the {b} shall return all property, documents and data belonging to the {a}."]),
    ],
    "Freelance Work Contract": [
        ("SCOPE OF SERVICES", [
            "The {a} agrees to provide to the {b} the services described in this Agreement and any written statement of work agreed between the Parties.",
            "Deliverables, milestones and timelines shall be as agreed in writing; any change to the scope requires the written consent of both Parties."]),
        ("FEES AND PAYMENT", [
            "The {b} shall pay the {a} the fees agreed between the Parties, in accordance with the payment schedule set out in this Agreement.",
            "Invoices shall be paid within the period stated in this Agreement; overdue amounts may attract interest at a reasonable rate.",
            "Unless otherwise agreed, all fees are exclusive of applicable taxes."]),
        ("INDEPENDENT CONTRACTOR", [
            "The {a} is an independent contractor and nothing in this Agreement creates an employment, partnership or agency relationship.",
            "The {a} is solely responsible for its own taxes, insurance, tools and working methods."]),
        ("INTELLECTUAL PROPERTY", [
            "Upon receipt of full payment, all rights in the final deliverables shall transfer to the {b}.",
            "The {a} retains ownership of its pre-existing tools, methods and materials."]),
        ("CONFIDENTIALITY", [
            "Each Party shall keep confidential all proprietary and sensitive information received from the other Party and shall not disclose it to any third party without prior written consent, except as required by law."]),
        ("TERM AND TERMINATION", [
            "This Agreement begins on the Effective Date and continues until completion of the services unless terminated earlier.",
            "Either Party may terminate this Agreement by written notice if the other Party commits a material breach that is not remedied within a reasonable period after notice.",
            "On termination the {b} shall pay for all services performed up to the date of termination."]),
    ],
    "Lease Agreement": [
        ("PREMISES AND PURPOSE", [
            "The {a} lets to the {b}, and the {b} takes on lease, the premises described in the schedule or terms of this Agreement (the \"Premises\").",
            "The {b} shall use the Premises only for the purpose agreed between the Parties and in compliance with applicable law."]),
        ("RENT AND SECURITY DEPOSIT", [
            "The {b} shall pay the rent agreed between the Parties on or before the due date of each period.",
            "The {b} shall pay a refundable security deposit, which the {a} may apply against unpaid rent or damage beyond normal wear and tear.",
            "The security deposit shall be returned within a reasonable period after the {b} vacates and returns the Premises."]),
        ("USE AND MAINTENANCE", [
            "The {b} shall keep the Premises clean and in good condition and shall promptly report any damage or defect to the {a}.",
            "The {b} shall not sublet, assign or alter the Premises without the prior written consent of the {a}.",
            "The {a} shall be responsible for structural repairs unless the damage is caused by the {b}."]),
        ("ENTRY AND INSPECTION", [
            "The {a} may enter the Premises at reasonable times and on reasonable prior notice to inspect, repair or show the Premises."]),
        ("TERM AND TERMINATION", [
            "The lease shall run for the period stated in this Agreement, beginning on the Effective Date.",
            "Either Party may terminate the lease by giving written notice as agreed between the Parties.",
            "On expiry or termination the {b} shall vacate the Premises and hand over possession in the condition received, fair wear and tear excepted."]),
    ],
    "Non-Disclosure Agreement": [
        ("CONFIDENTIAL INFORMATION", [
            "\"Confidential Information\" means all non-public information, in any form, disclosed by the {a} to the {b}, including business, technical, financial and customer information that is marked confidential or would reasonably be understood to be confidential."]),
        ("OBLIGATIONS OF THE RECEIVING PARTY", [
            "The {b} shall use the Confidential Information only for the purpose for which it was disclosed.",
            "The {b} shall protect the Confidential Information with at least the same degree of care it uses for its own confidential information, and no less than reasonable care.",
            "The {b} shall not disclose the Confidential Information to any third party except to its employees or advisers who need to know it and are bound by equivalent duties of confidentiality."]),
        ("EXCLUSIONS", [
            "These obligations do not apply to information that is or becomes public through no fault of the {b}, was already lawfully known to the {b}, is independently developed by the {b}, or is lawfully received from a third party without restriction.",
            "The {b} may disclose Confidential Information where required by law, after giving the {a} prompt notice where lawful."]),
        ("RETURN OR DESTRUCTION", [
            "On written request, the {b} shall promptly return or destroy all Confidential Information and confirm in writing that it has done so."]),
        ("DURATION", [
            "The obligations in this Agreement continue for the period stated in this Agreement, or, if none is stated, for a period of five (5) years from the Effective Date."]),
        ("REMEDIES", [
            "The Parties acknowledge that breach of this Agreement may cause irreparable harm and that the {a} may seek injunctive relief in addition to any other remedy available at law."]),
    ],
    "Service Agreement": [
        ("SERVICES", [
            "The {a} shall provide the services described in this Agreement to the {b} with reasonable skill, care and diligence.",
            "Any additional services shall be agreed in writing between the Parties."]),
        ("FEES AND PAYMENT", [
            "The {b} shall pay the {a} the fees agreed between the Parties in accordance with the payment terms of this Agreement.",
            "Undisputed invoices not paid when due may attract interest at a reasonable rate."]),
        ("WARRANTIES", [
            "The {a} warrants that it has the skills, experience and authority to perform the services and that the services will comply with applicable law.",
            "The {b} shall provide the information and cooperation reasonably required for the {a} to perform the services."]),
        ("CONFIDENTIALITY", [
            "Each Party shall keep confidential all non-public information of the other Party and use it only for the purposes of this Agreement."]),
        ("LIMITATION OF LIABILITY", [
            "Neither Party shall be liable to the other for any indirect, incidental or consequential loss, except where liability cannot be excluded by law.",
            "The total liability of the {a} under this Agreement shall not exceed the fees paid or payable under this Agreement."]),
        ("TERM AND TERMINATION", [
            "This Agreement begins on the Effective Date and continues for the term stated in this Agreement unless terminated earlier.",
            "Either Party may terminate this Agreement by written notice for material breach not remedied within a reasonable period after notice."]),
    ],
    "Partnership Agreement": [
        ("NATURE AND PURPOSE", [
            "The Parties agree to carry on business together as partners under the name and for the purposes agreed between them.",
            "The partnership shall commence on the Effective Date and continue until dissolved in accordance with this Agreement."]),
        ("CAPITAL CONTRIBUTIONS", [
            "The {a} and the {b} shall contribute capital in the amounts agreed between them, and no partner shall withdraw capital without the consent of the other."]),
        ("PROFITS AND LOSSES", [
            "Profits and losses of the partnership shall be shared between the partners in the proportions agreed between them, or equally if none are agreed.",
            "Each partner shall be entitled to a fair share of the profits, calculated and distributed at agreed intervals."]),
        ("MANAGEMENT AND DECISIONS", [
            "Each partner shall take part in the management of the business and act in good faith towards the other.",
            "Major decisions, including borrowing, admitting new partners and disposing of assets, require the consent of all partners."]),
        ("BOOKS AND ACCOUNTS", [
            "Proper books of account shall be kept at the principal place of business and shall be open to inspection by every partner."]),
        ("DISSOLUTION AND EXIT", [
            "The partnership may be dissolved by mutual written consent or as provided by law.",
            "A partner wishing to leave shall give written notice as agreed between the partners, and the remaining partners shall have the first option to purchase the leaving partner's share."]),
    ],
    "Offer Letter": [
        ("POSITION AND START DATE", [
            "The {a} offers the {b} employment in the position discussed between the Parties, commencing on the Effective Date or such other date as both Parties agree in writing.",
            "The {b} shall report to the person designated by the {a} and perform the duties reasonably associated with the position."]),
        ("COMPENSATION AND BENEFITS", [
            "The {b} shall receive the compensation and benefits described in this Agreement, subject to applicable deductions and taxes.",
            "The {b} shall be entitled to leave and other benefits in accordance with the {a}'s policies."]),
        ("CONDITIONS OF OFFER", [
            "This offer is conditional on satisfactory verification of the {b}'s identity, qualifications and references, and on any probationary period stated in this Agreement."]),
        ("CONFIDENTIALITY", [
            "The {b} shall keep confidential all non-public information of the {a} during and after employment."]),
        ("ACCEPTANCE", [
            "This offer may be accepted by signing and returning a copy of this Agreement. Unless accepted within the period allowed by the {a}, the offer shall lapse."]),
    ],
}

# Standard clauses added to every document
GENERIC = [
    ("FORCE MAJEURE", [
        "Neither Party shall be liable for any failure or delay in performing its obligations where the failure or delay results from events beyond its reasonable control, including natural disaster, war, epidemic, governmental action or failure of public utilities.",
        "The affected Party shall promptly notify the other Party and resume performance as soon as reasonably practicable."]),
    ("NOTICES", [
        "Any notice under this Agreement shall be in writing and delivered by hand, registered post or email to the address of the receiving Party stated in this Agreement, and is deemed received on delivery."]),
    ("DISPUTE RESOLUTION", [
        "The Parties shall first attempt to resolve any dispute arising out of this Agreement through good-faith negotiation.",
        "If the dispute is not resolved within thirty (30) days, it shall be referred to the competent courts of [City / Jurisdiction]."]),
    ("GOVERNING LAW", [
        "This Agreement shall be governed by and construed in accordance with the laws of [Jurisdiction]."]),
    ("ENTIRE AGREEMENT", [
        "This Agreement constitutes the entire agreement between the Parties on its subject matter and supersedes all prior discussions, representations and understandings."]),
    ("AMENDMENT AND WAIVER", [
        "This Agreement may be amended only by a written document signed by both Parties.",
        "No failure or delay in exercising any right shall operate as a waiver of that right."]),
    ("SEVERABILITY", [
        "If any provision of this Agreement is found to be invalid or unenforceable, the remaining provisions shall continue in full force and effect."]),
]


# ------------------------------------------------------------------ shared helpers
class GenResult(NamedTuple):
    text: str
    source: str          # "gemini" | "template"
    model: str = ""      # Gemini model that produced the text ("" for the template)
    warning: str = ""    # why the AI draft was not used (empty when all is well / no key set)


def _split_parties(parties: str) -> list[str]:
    """Split 'ABC Company and John Doe' into ['ABC Company', 'John Doe'] (legacy single-string input)."""
    names = [p.strip() for p in re.split(r"\s+and\s+|\s*&\s*|;|\n", parties) if p.strip()]
    return names or [parties.strip()]


def _fmt_date(d: date) -> str:
    return d.strftime("%B %d, %Y").replace(" 0", " ")


def _normalise(doc_type: str, details: dict | None, parties: str = "", terms: str = "") -> dict[str, str]:
    """Clean the details dict and fold in the legacy `parties` / `terms` strings if given."""
    out = {k: str(v).strip() for k, v in (details or {}).items() if v is not None and str(v).strip()}
    if parties.strip() and not out.get("party1_name"):
        names = _split_parties(parties)
        out["party1_name"] = names[0]
        if len(names) > 1:
            out.setdefault("party2_name", " and ".join(names[1:]))
    if terms.strip():
        out.setdefault("additional_terms", terms.strip())
    return out


def _party_block(doc_type: str, d: dict[str, str]) -> tuple[str, str, str, str]:
    """(name1, address1, name2, address2) with sensible fall-backs."""
    return (d.get("party1_name", "[First Party]"), d.get("party1_address", ""),
            d.get("party2_name", "[Second Party]"), d.get("party2_address", ""))


def _split_terms(terms: str) -> list[str]:
    return [t.strip().rstrip(".") for t in re.split(r";|\n", terms) if t.strip()]


def _key_items(doc_type: str, d: dict[str, str]) -> list[str]:
    """'Label: value.' lines for every filled key-detail field."""
    items = []
    for f in get_fields(doc_type):
        if f.group == "Key details" and d.get(f.key):
            items.append(f"{f.label}: {pretty_value(f, d[f.key]).rstrip('.')}.")
    if doc_type == "Non-Disclosure Agreement" and d.get("nda_type", "").startswith("Two-way"):
        items.append("This is a mutual agreement: each Party may disclose and receive Confidential Information, "
                     "and the obligations of confidentiality apply to each Party equally.")
    return items


# ------------------------------------------------------------------ offline template
def _template_document(doc_type: str, d: dict[str, str], eff_date: date) -> str:
    """Offline fallback: build a full agreement (recitals, numbered clauses, signatures)."""
    a, b = ROLES.get(doc_type, ("First Party", "Second Party"))
    n1, addr1, n2, addr2 = _party_block(doc_type, d)
    blank = "____________________________________"
    dt = _fmt_date(eff_date)
    fill = lambda s: s.format(a=a, b=b)
    law = d.get("governing_law", "")

    L = [doc_type.upper(), f"Effective Date: {dt}", "",
         f'This {doc_type} (the "Agreement") is made and entered into on {dt}.', "", "BETWEEN", "",
         f'**{n1}**, of {addr1 or blank} (hereinafter referred to as the "**{a}**"),', "", "AND", "",
         f'**{n2}**, of {addr2 or blank} (hereinafter referred to as the "**{b}**"),', "",
         '(each a "Party" and together the "Parties").', "", "RECITALS", "",
         "A. " + fill(PURPOSE.get(doc_type, "The Parties wish to enter into this Agreement.")),
         "B. The Parties wish to record the terms of their agreement in writing.", "",
         "NOW, THEREFORE, in consideration of the mutual covenants in this Agreement, the Parties agree as follows:", ""]

    n = 0

    def add(heading: str, clauses: list[str]) -> None:
        nonlocal n
        n += 1
        L.append(f"{n}. {heading}")
        L.extend(f"{n}.{i} {fill(c)}" for i, c in enumerate(clauses, 1))
        L.append("")

    add("DEFINITIONS AND INTERPRETATION", [
        f'In this Agreement, "Effective Date" means {dt}, and "Agreement" means this {doc_type} including any schedules and written amendments.',
        "Headings are for convenience only and do not affect interpretation.",
        "References to a Party include its successors and permitted assigns."])
    items = _key_items(doc_type, d)
    if items:
        add("KEY TERMS", ["The Parties have agreed the following key terms, which apply throughout this Agreement:"] + items)
    for heading, clauses in CLAUSES.get(doc_type, CLAUSES["Service Agreement"]):
        add(heading, clauses)
    extra = _split_terms(d.get("additional_terms", ""))
    if extra:
        add("SPECIFIC TERMS AND CONDITIONS",
            ["The Parties have specifically agreed to the following terms, which form an integral part of this Agreement:"]
            + [f"{t[0].upper() + t[1:]}." for t in extra])
    for heading, clauses in GENERIC:
        if law:
            clauses = [c.replace("[City / Jurisdiction]", law).replace("[Jurisdiction]", law) for c in clauses]
        add(heading, clauses)

    L += ["IN WITNESS WHEREOF, the Parties have executed this Agreement on the date first written above.", "", "SIGNATURES", ""]
    for name, role in [(n1, a), (n2, b)]:
        L += [f"For and on behalf of **{name}** ({role})", "Signature: ______________________________",
              "Name: __________________________________", "Date: ___________________________________", ""]
    L += ["WITNESSES", "1. Name: ____________________   Signature: ____________________",
          "2. Name: ____________________   Signature: ____________________"]
    return "\n".join(L)


# ------------------------------------------------------------------ Gemini
DEFAULT_MODELS = ("gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash")
API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
SYSTEM_PROMPT = ("You are a senior legal drafter. You write complete, formal, precise agreements in plain English. "
                 "You use every fact the user supplies exactly as given and never invent names, amounts, dates or addresses. "
                 "Where a necessary fact is missing you insert a short [Bracketed Placeholder] instead of guessing.")


# Output languages. Gemini drafts in them; the offline template is English only.
LANGUAGES = {"English": "English", "Tamil": "Tamil (தமிழ்)", "Hindi": "Hindi (हिन्दी)"}

LANGUAGE_RULES = """
LANGUAGE: Write the ENTIRE document in {language}, in a formal legal register used in Indian agreements.
- Keep party names, addresses, numbers, dates and currency amounts (including the rupee sign) exactly as supplied; do not translate or transliterate names.
- {language} has no upper-case letters, so mark every heading line by starting it with "# " (this is the one exception to the "no markdown headings" rule; for example "# 1. <heading>",
  "# RECITALS", "# SIGNATURES", "# WITNESSES" - each written in {language} - and the BETWEEN / AND lines).
- Keep the numbering exactly as specified (1., 1.1, A.).
- Signature, name and date lines must keep the form "<label>: ______________________" with the label in {language}.
- Where a legal term is normally used in English in Indian practice (for example "Security Deposit"), you may put the English term in brackets after the {language} term once."""


class GeminiError(Exception):
    def __init__(self, status: int | None, message: str):
        super().__init__(message)
        self.status, self.message = status, message

    @property
    def fatal(self) -> bool:
        """A rejected API key will fail for every model, so do not try the next one."""
        return self.status == 401 or (self.status == 400 and "api key" in self.message.lower())


def configured_models() -> list[str]:
    """GEMINI_MODEL first, then GEMINI_FALLBACK_MODELS, then the built-in defaults (no duplicates)."""
    wanted = [os.getenv("GEMINI_MODEL", "").strip()]
    wanted += [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "").split(",")]
    wanted += DEFAULT_MODELS
    seen, chain = set(), []
    for m in wanted:
        if m and m not in seen:
            seen.add(m)
            chain.append(m)
    return chain


def _thinking_level() -> str:
    level = os.getenv("GEMINI_THINKING_LEVEL", "medium").strip().lower()
    return level if level in ("low", "medium", "high") else "medium"  # 'minimal' is not supported by 3.8 Flash


def _build_prompt(doc_type: str, d: dict[str, str], eff_date: date, language: str = "English") -> str:
    a, b = ROLES[doc_type]
    n1, addr1, n2, addr2 = _party_block(doc_type, d)
    dt = _fmt_date(eff_date)
    lines = [f"- {a}: {n1}" + (f" (address: {addr1})" if addr1 else " (address not provided - use a ______ blank)"),
             f"- {b}: {n2}" + (f" (address: {addr2})" if addr2 else " (address not provided - use a ______ blank)")]
    details = [f"- {f.label}: {pretty_value(f, d[f.key])}" for f in get_fields(doc_type)
               if f.group == "Key details" and d.get(f.key)]
    topics = ", ".join(h for h, _ in CLAUSES.get(doc_type, []))
    extra = _split_terms(d.get("additional_terms", ""))
    mutual = doc_type == "Non-Disclosure Agreement" and d.get("nda_type", "").startswith("Two-way")
    lang_block = LANGUAGE_RULES.format(language=LANGUAGES[language]) if language != "English" else ""
    return f"""Draft a complete, formal, professional {doc_type}.

Effective date: {dt}

PARTIES
{chr(10).join(lines)}

KEY DETAILS (use each one exactly as written, in the most fitting clause)
{chr(10).join(details) or "- (none provided)"}

ADDITIONAL TERMS FROM THE USER (include every one faithfully as its own sub-clause under "SPECIFIC TERMS AND CONDITIONS")
{chr(10).join("- " + t for t in extra) or "- (none)"}

GOVERNING LAW / JURISDICTION: {d.get("governing_law") or "not provided - use [Jurisdiction] placeholders"}
{"This is a MUTUAL NDA: both parties disclose and receive confidential information, so make every obligation reciprocal." if mutual else ""}

Cover at least these topics for a {doc_type}: {topics}; plus term and termination, liability, force majeure, notices, dispute resolution, governing law, entire agreement, amendment and severability.

Structure (follow exactly):
1. Line 1: the document title in ALL CAPS. Line 2: "Effective Date: {dt}".
2. An opening sentence stating the agreement is made on that date, then BETWEEN / AND blocks naming each party
   (party names in **double asterisks**, with "of <address or ______>" and the defined role in quotes).
3. RECITALS (A., B.) followed by a "NOW, THEREFORE ..." sentence.
4. Numbered sections with ALL-CAPS headings on their own line (e.g. "1. DEFINITIONS AND INTERPRETATION"),
   each containing numbered sub-clauses on separate lines ("1.1 ...", "1.2 ...").
5. End with "IN WITNESS WHEREOF ...", a SIGNATURES section (name, signature, date lines per party) and WITNESSES.

Formatting rules: plain text only; no markdown headings, tables or code fences; one blank line between sections;
use "- " only for genuine bullet lists. No commentary before or after the document.
{lang_block}"""


def _post(model: str, key: str, body: dict) -> dict:
    resp = requests.post(f"{API_ROOT}/{model}:generateContent", json=body, timeout=(10, 150),
                         headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    if resp.status_code >= 400:
        try:
            msg = resp.json().get("error", {}).get("message", "")
        except ValueError:
            msg = resp.text[:200]
        raise GeminiError(resp.status_code, msg or resp.reason or "request failed")
    return resp.json()


def _extract(data: dict) -> tuple[str, str]:
    """(text, finishReason) of the first candidate; thought summaries are skipped."""
    cands = data.get("candidates") or [{}]
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return text, cands[0].get("finishReason", "")


def _try_model(model: str, key: str, prompt: str, language: str = "English") -> str:
    """One model, with a retry for transient errors / truncated drafts. Raises GeminiError on failure."""
    config: dict = {"maxOutputTokens": 32768, "thinkingConfig": {"thinkingLevel": _thinking_level()}}
    body = {"systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": config}
    last: GeminiError | None = None
    for attempt in range(3):
        try:
            data = _post(model, key, body)
        except GeminiError as e:
            if e.status == 400 and "thinkingConfig" in config and re.search(r"think", e.message, re.I):
                config.pop("thinkingConfig")      # older model without thinking levels: retry without it
                last = e
                continue
            if e.status in (429, 500, 502, 503, 504) and attempt < 2:
                last = e
                time.sleep(2 * (attempt + 1))
                continue
            raise
        text, finish = _extract(data)
        text = _clean_ai_text(text, keep_headings=language != "English")
        if _looks_complete(text, language):
            return text
        last = GeminiError(None, f"incomplete draft (finishReason={finish or 'unknown'})")
    raise last or GeminiError(None, "empty response")


def _gemini_document(doc_type: str, d: dict[str, str], eff_date: date, key: str, language: str = "English") -> tuple[str, str]:
    """Return (text, model). Tries each configured model in order."""
    prompt = _build_prompt(doc_type, d, eff_date, language)
    errors: list[str] = []
    last: GeminiError | None = None
    for model in configured_models():
        try:
            return _try_model(model, key, prompt, language), model
        except GeminiError as e:
            if e.fatal:
                raise
            last = e
            errors.append(f"{model}: {e.message[:120]}")
    raise GeminiError(last.status if last else None, " | ".join(errors) or "no model available")


def _clean_ai_text(text: str, keep_headings: bool = False) -> str:
    """Normalise model output to the app's plain-text conventions."""
    text = re.sub(r"^```\w*\n|\n```$", "", text.strip())
    out = []
    for line in text.replace("\r", "").split("\n"):
        line = re.sub(r"^#{1,6}\s*", "# " if keep_headings else "", line)   # markdown headings -> plain / "# " marker
        line = re.sub(r"^\s*[*\u2022]\s+", "- ", line)              # "* item" / "• item" -> "- item"
        line = re.sub(r"^\*\*(\d+\.\s+[^*]+)\*\*$", r"\1", line)    # "**1. HEADING**" -> "1. HEADING"
        out.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _looks_complete(text: str, language: str = "English") -> bool:
    """Cheap sanity check: long enough, has numbered clauses and reaches the signature block."""
    if language != "English":   # no upper-case / "SIGNATURES" in Tamil or Hindi: look for the blank signature lines instead
        return len(text) > 1000 and bool(re.search(r"^\d+\.\d+\s", text, re.M)) and "____" in text[-800:]
    return len(text) > 1500 and bool(re.search(r"^\d+\.\d+\s", text, re.M)) and "SIGNATURES" in text.upper()


def _explain(e: GeminiError) -> str:
    """Short, human reason shown in the UI when the AI draft could not be used."""
    if e.fatal:
        return "Gemini rejected the API key - check GEMINI_API_KEY in your .env file."
    if e.status == 429:
        return "Gemini rate limit or quota reached - try again shortly. " + e.message[:100]
    if e.status in (403, 404):
        return f"The configured Gemini model is not available to this key ({e.message[:140]})."
    return f"Gemini could not complete the draft ({e.message[:160]})."


def generate_document(doc_type: str, details: dict | None, eff_date: date, parties: str = "", terms: str = "",
                      language: str = "English") -> GenResult:
    """Draft the document with Gemini, or with the built-in template if the AI is unavailable."""
    if doc_type not in ROLES:
        raise ValueError(f"Unknown document type: {doc_type}")
    if language not in LANGUAGES:
        raise ValueError(f"Unsupported language: {language}. Choose one of: {', '.join(LANGUAGES)}")
    d = _normalise(doc_type, details, parties, terms)
    key = os.getenv("GEMINI_API_KEY", "").strip()
    warning = ""
    if key and key != "your_api_key":
        try:
            text, model = _gemini_document(doc_type, d, eff_date, key, language)
            return GenResult(text, "gemini", model)
        except GeminiError as e:
            warning = _explain(e)
        except requests.RequestException as e:   # no network, DNS, timeout...
            warning = f"Could not reach Gemini ({type(e).__name__})."
        except Exception as e:                   # never let an AI problem break the app
            warning = f"AI drafting failed ({type(e).__name__}: {str(e)[:100]})."
    if language != "English":
        warning = (f"{language} drafting needs Gemini, so this is the English template. " + warning).strip()
    return GenResult(_template_document(doc_type, d, eff_date), "template", "", warning)
