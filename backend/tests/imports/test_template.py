"""The import template over HTTP (SPEC section 8 `GET /imports/template/`, DESIGN 1.5)."""

import io

import pytest
from openpyxl import load_workbook

from apps.compensation.validators import IDENTITY_COLUMNS, check_header
from apps.core.queries import active_components

pytestmark = pytest.mark.django_db

URL = "/api/v1/imports/template/"


def header_of(response) -> tuple[list, str | None]:
    sheet = load_workbook(io.BytesIO(response.content)).worksheets[0]
    return [cell.value for cell in sheet[1]], sheet.freeze_panes


@pytest.mark.parametrize("country", ["IN", "in"])
def test_a_country_template_has_its_components_in_order_under_a_frozen_header(
    api, lookups, country
):
    response = api.get(URL, {"country": country})

    assert response.status_code == 200
    assert response["Content-Type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response["Content-Disposition"] == (
        'attachment; filename="acme-import-template-IN.xlsx"'
    )
    header, frozen = header_of(response)
    assert header == [
        *IDENTITY_COLUMNS,
        "BASE",
        "HRA",
        "ALLOWANCES",
        "TAX",
        "EMPLOYER_CONTRIBUTION",
    ]
    assert frozen == "A2"


def test_without_a_country_the_template_carries_every_component(api, lookups):
    response = api.get(URL)

    header, _ = header_of(response)
    assert response["Content-Disposition"] == 'attachment; filename="acme-import-template.xlsx"'
    assert header[len(IDENTITY_COLUMNS) :] == [c.code for c in active_components()]


def test_an_unknown_country_is_a_404(api, lookups):
    assert api.get(URL, {"country": "XX"}).status_code == 404


def test_the_template_reads_back_with_nothing_missing_or_unknown(api, lookups):
    header, _ = header_of(api.get(URL))

    result = check_header(header, [c.code for c in active_components()])

    assert (result.missing, result.unknown, result.rejected) == ([], [], False)
