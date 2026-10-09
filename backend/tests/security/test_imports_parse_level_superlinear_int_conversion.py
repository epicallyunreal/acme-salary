"""Guard: already closed by D68, which clips every cell to 256 characters at read, so a
longer level cell never matches as a number and never reaches Decimal.

Lead test for fingerprint ``imports_parse_level_superlinear_int_conversion``.

Claim: ``apps.imports.parser.parse_level`` converts an all-digit ``level`` cell with
``int(Decimal(given))`` whatever its length, during staging and before any rule or length
clip, although a valid level is 1 to 6. Under the C ``_decimal`` module that CPython loads
first, ``int(Decimal)`` is quadratic in the digit count (CPython's own note in
``Lib/_pylong.py``), so an over-long cell costs CPU out of proportion to its size.

The test posts a one-row CSV whose level cell is 10,000 digits and records the length of
every string handed to the ``Decimal`` name the parser uses. A string past the bound is
swapped for "0", so the test never performs the long conversion and behaves the same under
either decimal implementation. It asserts that no over-long string reached ``Decimal`` and
that the cell is still refused, as a row error on ``level`` or as a 400.
"""

from decimal import Decimal

import pytest

from apps.imports import parser
from apps.imports.models import ImportRow
from tests.imports.sheets import new_row, upload_of

pytestmark = pytest.mark.django_db

LIST = "/api/v1/imports/"
# Far past any level, yet well under csv.field_size_limit(), so the CSV reader keeps it.
OVERLONG_LEVEL = "9" * 10_000
# Generous: a whole level fits in a few characters, and a fix bounds the cell below this.
DIGIT_BOUND = 32


def test_an_overlong_level_cell_never_reaches_decimal_conversion(api, lookups, monkeypatch):
    seen: list[int] = []

    class TrackingDecimal(Decimal):
        """Records the length of every string the parser hands to Decimal. A string past
        the bound becomes "0", so the test itself does no long conversion."""

        def __new__(cls, value="0", context=None):
            if isinstance(value, str):
                seen.append(len(value))
                if len(value) > DIGIT_BOUND:
                    value = "0"
            return super().__new__(cls, value)

    # parse_level and parse_number resolve the module-global name; replace exactly that.
    monkeypatch.setattr(parser, "Decimal", TrackingDecimal)

    upload = upload_of(new_row(level=OVERLONG_LEVEL))
    response = api.post(LIST, {"file": upload}, format="multipart")

    longest = max(seen, default=0)
    assert longest <= DIGIT_BOUND, (
        f"staging handed a {longest:,}-character level cell to Decimal; parse_level must "
        "bound a cell's length before any arbitrary-precision conversion"
    )
    # D68's clip: the cell is kept to 256 characters and refused as a level, as a row error.
    assert response.status_code == 201, response.content
    row = ImportRow.objects.get(batch_id=response.json()["id"])
    assert row.status == ImportRow.Status.ERROR, row.messages
    assert [m["message"] for m in row.messages if m["field"] == "level"] == [
        "level must be between 1 and 6"
    ]
