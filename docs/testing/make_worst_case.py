"""Writes docs/testing/worst-case.xlsx, the end-to-end pass's worst-case sheet (PLAN step 13).

From backend/: uv run python ../docs/testing/make_worst_case.py

Five new employees at the edges the columns allow: the longest legacy code, full name, email and
designation, every earning, the bonus and the employer contribution on one record at their upper
bound, a long Polish name, a one-letter given name, a Devanagari name and a CJK name, levels 1 and
6, and joining dates on 1 April 2020, the reporting cut-off, and on 29 February 2024. Every row is valid, so the sheet can be approved
and its employees looked at in the directory and on their pages.
"""

from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook

OUT = Path(__file__).with_name("worst-case.xlsx")
# The upper bound of every amount and the bonus (apps/compensation/validators.py, D49).
MAX_AMOUNT = Decimal("9999999999.99")
# The longest values the columns hold (apps/employees/models.py, D55).
LEGACY_CODE_MAX, FULL_NAME_MAX, EMAIL_MAX, DESIGNATION_MAX = 32, 120, 254, 80

COMPONENTS = (
    "BASE",
    "AWS",
    "HOLIDAY_ALLOWANCE",
    "HRA",
    "ALLOWANCES",
    "TAX",
    "CPF",
    "NATIONAL_INSURANCE",
    "SOCIAL_INSURANCE",
    "EMPLOYER_CONTRIBUTION",
)
HEADER = (
    "legacy_code",
    "full_name",
    "email",
    "department",
    "designation",
    "level",
    "country_code",
    "gender",
    "joining_date",
    "last_date",
    "effective_from",
    "bonus_annual",
    *COMPONENTS,
)


def exactly(text: str, length: int) -> str:
    assert len(text) == length, (len(text), length, text)
    return text


def longest_email() -> str:
    """A local part of 64 and three domain labels of 63, 63 and 53 under `example`: 254."""
    local = "maximilian.alexander.konstantin.friedrich.von.hohenzollern.sigma"
    labels = [
        "the-longest-address-an-email-column-of-254-characters-can-hold1",
        "every-label-of-the-domain-at-sixty-three-characters-the-most-it",
        "is-allowed-by-the-dns-and-by-djangos-email-validator1",
    ]
    return f"{local}@{'.'.join(labels)}.example"


LONGEST = {
    "legacy_code": exactly("WC-LONGEST-CODE-THE-COLUMN-HOLDS", LEGACY_CODE_MAX),
    "full_name": exactly(
        "Maximilian Alexander Konstantin Friedrich von Hohenzollern-Sigmaringen "
        "Wolfeschlegelsteinhausenbergerdorff the Third Jr.",
        FULL_NAME_MAX,
    ),
    "email": exactly(longest_email(), EMAIL_MAX),
    "designation": exactly(
        "Principal Staff Engineer, Payments Platform Reliability, Observability and Tools",
        DESIGNATION_MAX,
    ),
}

ROWS = (
    {
        **LONGEST,
        "department": "engineering",
        "level": 6,
        "country_code": "IN",
        "gender": "undisclosed",
        "joining_date": date(2020, 4, 1),
        "bonus_annual": MAX_AMOUNT,
        "BASE": MAX_AMOUNT,
        "HRA": MAX_AMOUNT,
        "ALLOWANCES": MAX_AMOUNT,
        "EMPLOYER_CONTRIBUTION": MAX_AMOUNT,
    },
    {
        "legacy_code": "WC-2",
        "full_name": "Aleksandra Wiśniewska-Kowalczyk",
        "email": "aleksandra.wisniewska-kowalczyk@acme.example",
        "department": "finance",
        "designation": "Associate Financial Analyst",
        "level": 1,
        "country_code": "DE",
        "gender": "female",
        "joining_date": date(2024, 2, 29),
        "BASE": 52000,
        "TAX": 8000,
        "SOCIAL_INSURANCE": 10400,
        "EMPLOYER_CONTRIBUTION": 10400,
    },
    {
        "legacy_code": "WC-3",
        "full_name": "J Okafor",
        "email": "j.okafor@acme.example",
        "department": "sales",
        "designation": "Account Executive",
        "level": 2,
        "country_code": "US",
        "gender": "male",
        "joining_date": date(2020, 4, 1),
        "BASE": 98000,
        "TAX": 19600,
        "EMPLOYER_CONTRIBUTION": 7840,
    },
    {
        "legacy_code": "WC-4",
        "full_name": "अनन्या शर्मा",
        "email": "ananya.sharma.wc4@acme.example",
        "department": "data",
        "designation": "Senior Data Scientist",
        "level": 3,
        "country_code": "IN",
        "gender": "female",
        "joining_date": date(2024, 2, 29),
        "BASE": 1800000,
        "HRA": 720000,
        "ALLOWANCES": 450000,
        "TAX": 270000,
        "EMPLOYER_CONTRIBUTION": 216000,
    },
    {
        "legacy_code": "WC-5",
        "full_name": "陈美玲",
        "email": "chen.meiling.wc5@acme.example",
        "department": "design",
        "designation": "Lead Designer",
        "level": 4,
        "country_code": "SG",
        "gender": "female",
        "joining_date": date(2020, 4, 1),
        "BASE": 120000,
        "AWS": 10000,
        "TAX": 12000,
        "CPF": 24000,
        "EMPLOYER_CONTRIBUTION": 20400,
    },
)


def main() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Employees"
    sheet.append(HEADER)
    for row in ROWS:
        values = {**row, "effective_from": row["joining_date"]}
        sheet.append([values.get(column) for column in HEADER])
    workbook.save(OUT)
    print(f"wrote {OUT.name}: {len(ROWS)} rows")


if __name__ == "__main__":
    main()
