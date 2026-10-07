"""The import template (SPEC section 8 `GET /imports/template/`, DESIGN 1.5)."""

from __future__ import annotations

import io

from django.http import Http404
from openpyxl import Workbook

from apps.core import queries as core_queries
from apps.core.models import Country
from apps.imports.parser import template_columns


def template_country(country_code: str | None) -> str | None:
    """The country asked for, upper-cased, or None for every country. Unknown is a 404."""
    if not country_code:
        return None
    code = country_code.strip().upper()
    if not Country.objects.filter(code=code).exists():
        raise Http404(f"Unknown country_code: {code}")
    return code


def build_template(country_code: str | None) -> bytes:
    """One header row, frozen: the identity columns, then the country's components in sort order,
    or every component when no country is given."""
    if country_code is None:
        components = list(core_queries.active_components())
    else:
        components = core_queries.components_for_country(country_code)
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Employees")
    # Write-only sheets take the pane before any row is written.
    sheet.freeze_panes = "A2"
    sheet.append(template_columns(component.code for component in components))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
