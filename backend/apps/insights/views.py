"""GET /api/v1/insights/<name>/ (SPEC section 8). Parses the filters and hands them to the query."""

from django.http import Http404
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import fx
from apps.core.dates import parse_on
from apps.core.filters import parse_bool, parse_csv
from apps.core.money import render
from apps.insights import queries


class InsightView(APIView):
    """No serializer: the shapes in DESIGN 1.6 are the contract, mirrored by the frontend types."""

    def get(self, request, name: str):
        insight = queries.INSIGHTS.get(name)
        if insight is None:
            raise Http404
        params = request.query_params
        lookups = queries.Lookups.load()
        filters = queries.build_filters(
            lookups,
            country=parse_csv(params.get("country")),
            department=parse_csv(params.get("department")),
            include_exited=parse_bool(params.get("include_exited")),
            on=parse_on(params.get("on")),
            currency=params.get("currency"),
        )
        rates = fx.RateTable.load(filters.on)
        return Response(render(insight(filters, rates, lookups)))
