"""GET /api/v1/exports/employees/ and /exports/insights/<name>/ (SPEC F6, section 8).

Each view parses what the directory or the insight endpoint parses, through the same code, and
hands the table to a writer. CSV streams. XLSX and JSON are built whole before they are sent
(DESIGN 1.7).
"""

from datetime import date
from itertools import chain, islice

from django.http import Http404, HttpResponse, QueryDict, StreamingHttpResponse
from django.utils import timezone
from rest_framework.generics import GenericAPIView
from rest_framework.views import APIView

from apps.core.exceptions import Invalid, clip
from apps.employees.views import DirectoryMixin
from apps.exports import tables, writers
from apps.insights.views import answer

CONTENT_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "json": "application/json",
}
# What each export reads besides `on` and `currency`, and so what its JSON file says it applied.
DIRECTORY_FILTERS = (*DirectoryMixin.filterset_class.base_filters, "search")
INSIGHT_FILTERS = ("country", "department", "include_exited")


def parse_file(value: str | None) -> str:
    """`csv`, `xlsx` or `json`, in any case. Anything else, or nothing, is a 400."""
    given = (value or "").strip().lower()
    if given in CONTENT_TYPES:
        return given
    message = "file must be csv, xlsx or json"
    raise Invalid({"file": [f"{message}, got {clip(value)}" if value else message]})


def applied(params: QueryDict, keys: tuple[str, ...], on: date, currency: str) -> dict:
    """The filters the export read, as given, with the reporting date and currency as applied, so
    a JSON file says what its figures are in when the request left them to their defaults (D60).
    A parameter the export does not read is left out rather than shown as applied."""
    given = {key: params.get(key) for key in keys if key in params}
    return {**given, "on": on, "currency": currency}


def respond(table: tables.Table, file: str, what: str, filters: dict):
    """The file as an attachment named `acme-<what>-YYYYMMDD-HHMM.<ext>`, stamped in UTC (D27)."""
    stamp = timezone.now()
    headers = {
        "Content-Disposition": f'attachment; filename="acme-{what}-{stamp:%Y%m%d-%H%M}.{file}"'
    }
    if file == "csv":
        # The first rows are read before the 200 goes out, so a query that fails is an error
        # response rather than a file cut off part way.
        rows = iter(table.rows)
        first = list(islice(rows, writers.BATCH))
        return StreamingHttpResponse(
            writers.csv_stream(table.header, chain(first, rows)),
            content_type=CONTENT_TYPES[file],
            headers=headers,
        )
    if file == "xlsx":
        content = writers.xlsx_bytes(table.header, table.rows, sheet=what)
    else:
        content = writers.json_bytes(table.keys, table.rows, generated_at=stamp, filters=filters)
    return HttpResponse(content, content_type=CONTENT_TYPES[file], headers=headers)


class ExportEmployeesView(DirectoryMixin, GenericAPIView):
    """Every row the directory's filters, search and ordering leave, whatever page is showing."""

    def get(self, request):
        file = parse_file(request.query_params.get("file"))
        on, currency, rates = self.reporting()
        employees = self.filter_queryset(self.get_queryset())
        table = tables.directory_table(employees, on=on, rates=rates, currency=currency)
        filters = applied(request.query_params, DIRECTORY_FILTERS, on, currency)
        return respond(table, file, "employees", filters)


class ExportInsightView(APIView):
    """An insight's table. An unknown name is a 404 before anything else is read."""

    def get(self, request, name: str):
        if name not in tables.INSIGHT_TABLES:
            raise Http404
        file = parse_file(request.query_params.get("file"))
        payload, filters = answer(name, request.query_params)
        table = tables.INSIGHT_TABLES[name](payload)
        given = applied(request.query_params, INSIGHT_FILTERS, filters.on, filters.currency)
        return respond(table, file, name, given)
