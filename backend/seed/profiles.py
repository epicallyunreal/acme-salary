"""Every design parameter of the demo dataset (SPEC section 11, DESIGN section 5), as plain data.

Nothing here is a sourced statistic. Changing any value changes the seed and therefore the golden
hash in tests/seed/golden.txt, which the same commit regenerates.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

REFERENCE_DATE = date(2026, 10, 6)
REFERENCE_DATETIME = datetime(2026, 10, 6, tzinfo=UTC)

HR_MANAGER_EMAIL = "hr@acme.example"
# Reserved for examples by RFC 2606: no address can reach a real person, and the app sends none.
EMAIL_DOMAIN = "acme.example"
# The code the legacy HR system gave each seeded employee, unlike an ACME code on purpose:
# HR- and five digits, drawn without repeats (D48).
LEGACY_CODE_FORMAT = "HR-{}"
LEGACY_NUMBERS = range(10000, 100000)

NOISE_SIGMA = 0.18
BASE_ROUNDING = 100


@dataclass(frozen=True)
class ComponentSpec:
    code: str
    name: str
    kind: str
    country: str | None
    sort_order: int


COMPONENTS = (
    ComponentSpec("BASE", "Base salary", "earning", None, 10),
    ComponentSpec("HRA", "House rent allowance", "earning", "IN", 20),
    ComponentSpec("ALLOWANCES", "Allowances", "earning", "IN", 30),
    ComponentSpec("HOLIDAY_ALLOWANCE", "Holiday allowance", "earning", "NL", 20),
    ComponentSpec("AWS", "Annual wage supplement", "earning", "SG", 20),
    ComponentSpec("TAX", "Income tax", "deduction", None, 50),
    ComponentSpec("NATIONAL_INSURANCE", "National Insurance", "deduction", "GB", 60),
    ComponentSpec("SOCIAL_INSURANCE", "Social insurance", "deduction", "DE", 60),
    ComponentSpec("CPF", "CPF contribution", "deduction", "SG", 60),
    ComponentSpec(
        "EMPLOYER_CONTRIBUTION", "Employer contribution", "employer_contribution", None, 90
    ),
)


@dataclass(frozen=True)
class CountrySpec:
    code: str
    name: str
    currency: str
    share: float
    anchor: int  # level-3 base, annual, local currency
    min_gross: int
    employer_share: float  # EMPLOYER_CONTRIBUTION as a share of base
    components: dict[str, float]  # country component code -> share of base
    bonus_probability: float
    faker_locale: str


COUNTRIES = (
    CountrySpec(
        "IN",
        "India",
        "INR",
        0.45,
        1_450_000,
        400_000,
        0.12,
        {"HRA": 0.40, "ALLOWANCES": 0.25},
        0.25,
        "en_IN",
    ),
    CountrySpec("US", "United States", "USD", 0.20, 135_000, 35_000, 0.08, {}, 0.50, "en_US"),
    CountrySpec(
        "GB",
        "United Kingdom",
        "GBP",
        0.12,
        68_000,
        24_000,
        0.14,
        {"NATIONAL_INSURANCE": 0.10},
        0.45,
        "en_GB",
    ),
    CountrySpec(
        "DE",
        "Germany",
        "EUR",
        0.10,
        75_000,
        26_000,
        0.20,
        {"SOCIAL_INSURANCE": 0.20},
        0.45,
        "de_DE",
    ),
    CountrySpec(
        "NL",
        "Netherlands",
        "EUR",
        0.08,
        72_000,
        26_000,
        0.18,
        {"HOLIDAY_ALLOWANCE": 0.08},
        0.30,
        "nl_NL",
    ),
    # Faker has no Singapore locale; names come from en_US.
    CountrySpec(
        "SG",
        "Singapore",
        "SGD",
        0.05,
        100_000,
        30_000,
        0.17,
        {"AWS": 1 / 12, "CPF": 0.20},
        0.30,
        "en_US",
    ),
)


@dataclass(frozen=True)
class DepartmentSpec:
    code: str
    name: str
    share: float
    multiplier: float
    role: str  # the noun designations are built from


DEPARTMENTS = (
    DepartmentSpec("engineering", "Engineering", 0.30, 1.15, "Engineer"),
    DepartmentSpec("product", "Product", 0.05, 1.0, "Product Manager"),
    DepartmentSpec("design", "Design", 0.04, 1.0, "Designer"),
    DepartmentSpec("data", "Data", 0.05, 1.0, "Data Scientist"),
    DepartmentSpec("sales", "Sales", 0.15, 1.0, "Account Executive"),
    DepartmentSpec("marketing", "Marketing", 0.05, 1.0, "Marketing Specialist"),
    DepartmentSpec("customer-support", "Customer Support", 0.12, 0.8, "Support Specialist"),
    DepartmentSpec("finance", "Finance", 0.05, 1.0, "Financial Analyst"),
    DepartmentSpec("hr", "HR", 0.04, 1.0, "HR Partner"),
    DepartmentSpec("legal", "Legal", 0.02, 1.0, "Counsel"),
    DepartmentSpec("it", "IT", 0.05, 1.0, "IT Engineer"),
    DepartmentSpec("operations", "Operations", 0.08, 1.0, "Operations Analyst"),
)

LEVELS = (1, 2, 3, 4, 5, 6)
LEVEL_SHARES = {1: 0.25, 2: 0.25, 3: 0.20, 4: 0.15, 5: 0.10, 6: 0.05}
LEVEL_MULTIPLIERS = {1: 0.55, 2: 0.75, 3: 1.0, 4: 1.4, 5: 2.0, 6: 3.0}
LEVEL_TITLES = {
    1: "Associate {role}",
    2: "{role}",
    3: "Senior {role}",
    4: "Lead {role}",
    5: "Principal {role}",
    6: "Head of {department}",
}


def designation(department: DepartmentSpec, level: int) -> str:
    return LEVEL_TITLES[level].format(role=department.role, department=department.name)


# TAX as a share of gross by level band: a recorded projection, never computed from tax law.
TAX_SHARE_BY_LEVEL = {1: 0.10, 2: 0.10, 3: 0.20, 4: 0.20, 5: 0.30, 6: 0.30}

COMPONENT_JITTER = 0.05  # each component share is multiplied by uniform(1 - j, 1 + j)

BONUS_RANGE = (0.05, 0.15)  # share of base, for employees who get one

GENDER_SHARES = {"female": 0.48, "male": 0.50, "other": 0.01, "undisclosed": 0.01}

# 10,000 on staff on the reference date and 5,000 who left before it (D64).
ACTIVE_EMPLOYEES = 10_000
EXITED_EMPLOYEES = 5_000
HISTORY_START = date(2015, 1, 1)  # the earliest joining date
MIN_TENURE_DAYS = 30  # nobody leaves in their first 30 days

# Years of total experience, before joining and at ACME, for each level. Neighbours overlap by
# about a year, where the promotion between them falls, and L1 and L2 meet at 3 years (D64).
LADDER = {1: (0, 3), 2: (3, 6), 3: (5, 8), 4: (7, 11), 5: (10, 13), 6: (12, 30)}
# How much likelier each level is to leave than L3 to L6 (D64).
LEAVE_WEIGHTS = {1: 2.0, 2: 1.5, 3: 1.0, 4: 1.0, 5: 1.0, 6: 1.0}

RAISE_RANGE = (0.03, 0.08)  # an ordinary April raise
# Someone who joined in the six months before an April review skips it, no raise and no
# promotion, so a December joiner's first review is the April sixteen months on (D70).
FIRST_REVIEW_MONTHS = 6
# Everyone employed on the reporting cut-off, 1 April 2020, has a record starting that day. Where
# the pay running into it started earlier, a revision repeats it under this note (D70).
CUTOFF_NOTE = "Reporting cut-off, FY 2020-21: pay unchanged"
PROMOTION_RANGE = (0.12, 0.20)  # the April revision where the ladder moves someone up
EXPERIENCE_PAY = 0.02  # a year of experience above the level's floor
EXPERIENCE_PAY_CAP = 0.20

# Sixteen monthly rows (D22): four currencies to USD and four to EUR, September and October 2026.
RATES = (
    ("INR", "USD", date(2026, 9, 1), Decimal("0.01195")),
    ("GBP", "USD", date(2026, 9, 1), Decimal("1.3410")),
    ("EUR", "USD", date(2026, 9, 1), Decimal("1.1720")),
    ("SGD", "USD", date(2026, 9, 1), Decimal("0.7790")),
    ("INR", "EUR", date(2026, 9, 1), Decimal("0.01020")),
    ("GBP", "EUR", date(2026, 9, 1), Decimal("1.1440")),
    ("USD", "EUR", date(2026, 9, 1), Decimal("0.8530")),
    ("SGD", "EUR", date(2026, 9, 1), Decimal("0.6650")),
    ("INR", "USD", date(2026, 10, 1), Decimal("0.01200")),
    ("GBP", "USD", date(2026, 10, 1), Decimal("1.3450")),
    ("EUR", "USD", date(2026, 10, 1), Decimal("1.1750")),
    ("SGD", "USD", date(2026, 10, 1), Decimal("0.7810")),
    ("INR", "EUR", date(2026, 10, 1), Decimal("0.01021")),
    ("GBP", "EUR", date(2026, 10, 1), Decimal("1.1447")),
    ("USD", "EUR", date(2026, 10, 1), Decimal("0.8511")),
    ("SGD", "EUR", date(2026, 10, 1), Decimal("0.6647")),
)

# The business tables in the determinism scope (SPEC section 11 rule 8), in truncation order.
# The first six hold pay data and are what the demo reset empties (D72); the lookups and the
# rates that follow stay.
BUSINESS_TABLES = (
    "audit.AuditLog",
    "compensation.CompensationLine",
    "compensation.CompensationRecord",
    "imports.ImportRow",
    "imports.ImportBatch",
    "employees.Employee",
    "core.ExchangeRate",
    "core.SalaryComponent",
    "core.Department",
    "core.Country",
)
PAY_TABLES = BUSINESS_TABLES[:6]
