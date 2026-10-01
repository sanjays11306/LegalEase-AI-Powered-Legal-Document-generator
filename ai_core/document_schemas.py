"""Input schema for every document type: which fields the form shows and which are required.

The UI, the API and the generator all read from here, so adding a new document type or field
is a one-place change.  Values are always strings; date fields are ISO strings (YYYY-MM-DD).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str = "text"              # text | textarea | select | date
    required: bool = False
    placeholder: str = ""
    help: str = ""
    options: tuple[str, ...] = ()   # for kind == "select"
    group: str = "Key details"      # Parties | Key details | Additional


# (role of party 1, role of party 2)
ROLES = {
    "Employment Contract": ("Employer", "Employee"),
    "Freelance Work Contract": ("Service Provider", "Client"),
    "Lease Agreement": ("Landlord", "Tenant"),
    "Non-Disclosure Agreement": ("Disclosing Party", "Receiving Party"),
    "Service Agreement": ("Service Provider", "Client"),
    "Partnership Agreement": ("First Partner", "Second Partner"),
    "Offer Letter": ("Employer", "Candidate"),
}

DESCRIPTIONS = {
    "Employment Contract": "Terms of employment between an employer and an employee.",
    "Freelance Work Contract": "Project-based work between a freelancer and a client.",
    "Lease Agreement": "Rental of a residential or commercial property.",
    "Non-Disclosure Agreement": "Protects confidential information shared between parties.",
    "Service Agreement": "Services provided by one party to another for a fee.",
    "Partnership Agreement": "How two partners will run a business together.",
    "Offer Letter": "Formal job offer with position, pay and conditions.",
}


def _parties(doc_type: str, label1: str | None = None, label2: str | None = None) -> list[Field]:
    """Name + address for each party, labelled with that document type's roles."""
    a, b = ROLES[doc_type]
    l1, l2 = label1 or a, label2 or b
    return [
        Field("party1_name", f"{l1} name", required=True, group="Parties", placeholder="Full legal name"),
        Field("party1_address", f"{l1} address", group="Parties", placeholder="Street, city, PIN code"),
        Field("party2_name", f"{l2} name", required=True, group="Parties", placeholder="Full legal name"),
        Field("party2_address", f"{l2} address", group="Parties", placeholder="Street, city, PIN code"),
    ]


_SPECIFIC: dict[str, list[Field]] = {
    "Employment Contract": [
        Field("job_title", "Job title", required=True, placeholder="e.g. Senior Software Engineer"),
        Field("employment_type", "Employment type", "select",
              options=("Full-time", "Part-time", "Fixed-term", "Internship")),
        Field("salary", "Salary / compensation", required=True, placeholder="e.g. ₹60,000 per month"),
        Field("work_location", "Work location", required=True, placeholder="e.g. Head office / Remote"),
        Field("probation", "Probation period", placeholder="e.g. 3 months"),
        Field("notice_period", "Notice period", placeholder="e.g. 30 days"),
        Field("working_hours", "Working hours", placeholder="e.g. 9:30 AM – 6:30 PM, Mon–Fri"),
        Field("leave_benefits", "Leave & benefits", "textarea", placeholder="e.g. 18 days paid leave; health insurance"),
    ],
    "Freelance Work Contract": [
        Field("project_description", "Project description", "textarea", required=True,
              placeholder="What work will be done?"),
        Field("deliverables", "Deliverables", "textarea", placeholder="e.g. 5-page website; source files; user guide"),
        Field("fee", "Total fee", required=True, placeholder="e.g. ₹75,000"),
        Field("payment_schedule", "Payment schedule", "select",
              options=("Full payment on completion", "50% advance, 50% on completion", "Milestone-based",
                       "Monthly", "Weekly", "Hourly, invoiced monthly")),
        Field("deadline", "Delivery deadline", "date"),
        Field("revisions", "Revisions included", placeholder="e.g. 2 rounds"),
        Field("ip_ownership", "Ownership of final work", "select",
              options=("Transfers to client on full payment", "Freelancer keeps ownership; client gets a licence")),
    ],
    "Lease Agreement": [
        Field("property_address", "Property address", "textarea", required=True, placeholder="Full address of the premises"),
        Field("property_type", "Property type", "select", required=True,
              options=("Residential", "Commercial", "Industrial / warehouse", "Land / agricultural")),
        Field("monthly_rent", "Monthly rent", required=True, placeholder="e.g. ₹25,000"),
        Field("security_deposit", "Security deposit", required=True, placeholder="e.g. ₹1,00,000 (refundable)"),
        Field("lease_term", "Lease term", required=True, placeholder="e.g. 11 months"),
        Field("rent_due", "Rent due date", placeholder="e.g. 5th of every month"),
        Field("lock_in", "Lock-in period", placeholder="e.g. 3 months"),
        Field("rent_escalation", "Rent increase", placeholder="e.g. 5% on renewal"),
        Field("utilities", "Maintenance & utilities", "textarea",
              placeholder="e.g. Tenant pays electricity and water; building maintenance by Landlord"),
    ],
    "Non-Disclosure Agreement": [
        Field("nda_type", "NDA type", "select", required=True, options=("One-way (unilateral)", "Two-way (mutual)")),
        Field("duration", "Confidentiality duration", required=True, placeholder="e.g. 3 years"),
        Field("purpose", "Purpose of disclosure", "textarea", required=True,
              placeholder="e.g. Evaluating a potential software partnership"),
        Field("confidential_scope", "What is confidential", "textarea",
              placeholder="e.g. Source code, pricing, customer lists, business plans"),
        Field("return_period", "Return / destroy within", placeholder="e.g. 14 days of written request"),
    ],
    "Service Agreement": [
        Field("services", "Services to be provided", "textarea", required=True, placeholder="Describe the services"),
        Field("fees", "Fees", required=True, placeholder="e.g. ₹40,000 per month"),
        Field("service_term", "Agreement term", required=True, placeholder="e.g. 12 months"),
        Field("payment_terms", "Payment terms", placeholder="e.g. Invoiced monthly, due in 15 days"),
        Field("termination_notice", "Termination notice", placeholder="e.g. 30 days' written notice"),
        Field("service_levels", "Service levels / deliverables", "textarea",
              placeholder="e.g. Response within 4 business hours; monthly report"),
    ],
    "Partnership Agreement": [
        Field("business_name", "Partnership / business name", required=True, placeholder="e.g. Sunrise Traders"),
        Field("profit_sharing", "Profit & loss sharing", required=True, placeholder="e.g. 50:50"),
        Field("business_nature", "Nature of business", "textarea", required=True,
              placeholder="What will the partnership do?"),
        Field("capital", "Capital contributions", "textarea", required=True,
              placeholder="e.g. First Partner ₹5,00,000; Second Partner ₹5,00,000"),
        Field("principal_place", "Principal place of business", placeholder="Address"),
        Field("duration", "Duration", placeholder="e.g. Until dissolved"),
        Field("management", "Roles & decision-making", "textarea",
              placeholder="e.g. First Partner handles finance; major decisions need both partners"),
    ],
    "Offer Letter": [
        Field("job_title", "Job title", required=True, placeholder="e.g. Marketing Manager"),
        Field("department", "Department", placeholder="e.g. Marketing"),
        Field("compensation", "Compensation", required=True, placeholder="e.g. ₹8,00,000 per annum (CTC)"),
        Field("work_location", "Work location", required=True, placeholder="e.g. Head office / Remote"),
        Field("joining_date", "Joining date", "date", required=True),
        Field("offer_valid_until", "Offer valid until", "date"),
        Field("reporting_to", "Reports to", placeholder="e.g. Head of Marketing"),
        Field("probation", "Probation period", placeholder="e.g. 6 months"),
        Field("benefits", "Benefits", "textarea", placeholder="e.g. Health insurance; 18 days paid leave"),
    ],
}

# Shown for every document type
COMMON = [
    Field("governing_law", "Governing law & jurisdiction", group="Additional",
          placeholder="e.g. Laws of India; courts at Mumbai"),
    Field("additional_terms", "Additional terms & conditions", "textarea", group="Additional",
          placeholder="Anything else that must be in the document",
          help="Optional. Separate points with semicolons (;) - each becomes its own clause."),
]

DOCUMENT_TYPES = list(ROLES)
GROUP_ORDER = ("Parties", "Key details", "Additional")


def get_fields(doc_type: str) -> list[Field]:
    """Parties first, then the type-specific key details, then the common extras."""
    if doc_type not in ROLES:
        return []
    return _parties(doc_type) + _SPECIFIC[doc_type] + COMMON


def field_map(doc_type: str) -> dict[str, Field]:
    return {f.key: f for f in get_fields(doc_type)}


def missing_required(doc_type: str, values: dict[str, str]) -> list[str]:
    """Labels of required fields that are still empty."""
    return [f.label for f in get_fields(doc_type) if f.required and not str(values.get(f.key, "")).strip()]


def pretty_value(field: Field, value: str) -> str:
    """Human-readable value (ISO dates become 'March 5, 2026')."""
    value = str(value).strip()
    if field.kind == "date" and value:
        try:
            return date.fromisoformat(value).strftime("%B %d, %Y").replace(" 0", " ")
        except ValueError:
            pass
    return value


def to_dict(doc_type: str) -> list[dict]:
    """JSON-friendly schema for the API (GET /api/document-types)."""
    return [{"key": f.key, "label": f.label, "kind": f.kind, "required": f.required, "group": f.group,
             "placeholder": f.placeholder, "help": f.help, "options": list(f.options)} for f in get_fields(doc_type)]
