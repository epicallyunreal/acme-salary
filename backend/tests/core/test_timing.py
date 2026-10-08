"""The timing command's period cases (D70)."""

from datetime import date

from apps.core.management.commands.timing import period_cases


def test_the_period_cases_are_the_dashboards_presets_and_the_cut_off():
    assert period_cases(date(2026, 10, 7)) == {
        "last 3 months": "from=2026-07-08",
        "last 6 months": "from=2026-04-08",
        "FY to date": "from=2026-04-01",
        "last FY": "from=2025-04-01&to=2026-03-31",
        "since the cut-off": "from=2020-04-01",
    }
