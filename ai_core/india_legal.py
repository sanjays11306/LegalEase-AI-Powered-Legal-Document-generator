"""Plain-language notices about Indian formalities (stamp duty, registration, ...) shown on the preview page.

!! NOT LAWYER-REVIEWED !!  Have an Indian advocate check every string in NOTICES / lease_notice() before you
ship.  The texts are deliberately general ("usually", "check your state") because stamp duty, registration
rules and rent laws differ from state to state and change over time.

Background the notices rest on (verify these too):
  * Registration Act, 1908, s.17(1)(d): a lease for more than one year (or reserving a yearly rent) must be registered.
    That is why 11-month leases are common.
  * Indian Stamp Act, 1899 + state stamp laws: stamp duty is state-specific; an under-stamped instrument is not
    admissible in evidence until the duty and penalty are paid (s.35).
  * Indian Partnership Act, 1932, s.69: an unregistered firm cannot sue third parties on contracts.
  * Indian Contract Act, 1872, s.27: post-employment non-compete restraints are generally void.
"""
import re
from typing import NamedTuple


class Notice(NamedTuple):
    level: str    # "warn" (act before signing) | "info" (good to know)
    title: str
    text: str


STAMP = Notice(
    "warn", "Stamp paper",
    "Print this agreement on non-judicial stamp paper (or e-stamp it) of the value required in your state before "
    "signing. Stamp duty depends on the state and the type of document. An under-stamped agreement may not be "
    "accepted as evidence in court until the duty and a penalty are paid.")

_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
          "eleven": 11, "twelve": 12, "twenty": 20, "thirty": 30}
_TERM = re.compile(r"(\d+(?:\.\d+)?|" + "|".join(_WORDS) + r")\s*[- ]?\s*(year|yr|month|mo)s?\b", re.I)


def parse_term_months(text: str) -> float | None:
    """'11 months' -> 11, '2 years' -> 24, 'eleven months' -> 11, '3 years 6 months' -> 42; None if not understood."""
    total, found = 0.0, False
    for num, unit in _TERM.findall(text or ""):
        n = float(_WORDS.get(num.lower(), 0) or num)
        total += n * (12 if unit.lower().startswith(("y")) else 1)
        found = True
    return total if found else None


def lease_notice(term_text: str) -> Notice:
    months = parse_term_months(term_text)
    if months is None:
        return Notice("warn", "Lease registration",
                      "Could not read the lease term. A lease for more than one year generally has to be registered "
                      "with the Sub-Registrar; leases of 11 months or less are commonly left unregistered.")
    if months > 12:
        return Notice("warn", "This lease must be registered",
                      f"A lease term of {term_text.strip()} is longer than one year, so it generally has to be "
                      "registered with the Sub-Registrar (in addition to stamp duty). An unregistered long lease may "
                      "not be enforceable or accepted as evidence. Registration needs both parties (and usually two "
                      "witnesses) to appear.")
    return Notice("info", "Lease registration",
                  "Leases of up to 11 months are commonly left unregistered, but some states (for example Maharashtra, "
                  "for leave-and-license agreements) require registration or police intimation even for short terms. "
                  "Check your state's rules. Renewing repeatedly to avoid registration can be challenged.")


NOTICES: dict[str, list[Notice]] = {
    "Partnership Agreement": [
        Notice("warn", "Register the firm",
               "Registering the firm with the state Registrar of Firms is optional, but an unregistered firm (or its "
               "partners) generally cannot sue third parties to enforce contracts. Registration is usually worth doing."),
    ],
    "Employment Contract": [
        Notice("info", "Statutory benefits",
               "Depending on company size, location and pay, PF, ESI, gratuity, bonus and your state's Shops & "
               "Establishments rules may apply and cannot be waived by contract."),
    ],
    "Offer Letter": [
        Notice("info", "Statutory benefits",
               "Depending on company size, location and pay, PF, ESI, gratuity and bonus rules may apply. "
               "An offer letter is usually followed by a formal appointment letter."),
    ],
    "Freelance Work Contract": [
        Notice("info", "Tax",
               "GST registration and TDS deduction may apply depending on turnover and the nature of the services. "
               "Agree who handles them and state whether fees include GST."),
    ],
    "Service Agreement": [
        Notice("info", "Tax",
               "GST and TDS may apply to the fees. State whether fees are inclusive or exclusive of GST."),
    ],
}

_NON_COMPETE = re.compile(r"non[- ]?compete|not (?:to )?(?:work|compete)|restraint of trade", re.I)


def notices(doc_type: str, details: dict | None = None) -> list[Notice]:
    """Notices for this document, most urgent first. `details` is the form data (may be empty for opened drafts)."""
    d = details or {}
    out: list[Notice] = [STAMP]
    if doc_type == "Lease Agreement":
        out.append(lease_notice(d.get("lease_term", "")))
    out += NOTICES.get(doc_type, [])
    if doc_type in ("Employment Contract", "Offer Letter") and _NON_COMPETE.search(d.get("additional_terms", "")):
        out.append(Notice("warn", "Non-compete clause",
                          "Restrictions on working for a competitor AFTER employment ends are generally unenforceable "
                          "in India (Indian Contract Act s.27). Restrictions during employment, and confidentiality, are fine."))
    return sorted(out, key=lambda n: n.level != "warn")
