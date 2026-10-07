"""The health check and the four lookup endpoints under /meta/ (SPEC section 8)."""

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.http import Http404, HttpRequest, JsonResponse
from django.views.decorators.http import require_GET
from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import fx
from apps.core.dates import parse_on
from apps.core.models import Country, Department, SalaryComponent
from apps.core.money import render


@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    """Unauthenticated liveness check for Fly: one query proves the database answers.

    A plain Django view, so DRF's default IsAuthenticated does not apply (SPEC section 8).
    """
    get_user_model().objects.order_by().exists()
    return JsonResponse({"status": "ok"})


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ("code", "name", "currency_code", "min_gross_annual")


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ("id", "code", "name")


class ComponentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalaryComponent
        fields = ("id", "code", "name", "kind", "country", "sort_order")


class CountryListView(ListAPIView):
    serializer_class = CountrySerializer
    pagination_class = None
    queryset = Country.objects.order_by("code")


class DepartmentListView(ListAPIView):
    serializer_class = DepartmentSerializer
    pagination_class = None
    queryset = Department.objects.order_by("name")


class ComponentListView(ListAPIView):
    """`?country=IN` gives the global components plus India's; no country gives them all."""

    serializer_class = ComponentSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = SalaryComponent.objects.filter(is_active=True).order_by("sort_order", "code")
        code = self.request.query_params.get("country")
        if code:
            if not Country.objects.filter(code=code).exists():
                raise Http404(f"Unknown country_code: {code}")
            queryset = queryset.filter(Q(country__isnull=True) | Q(country_id=code))
        return queryset


class ExchangeRateView(APIView):
    """One row per pair effective on `on`, plus the month label per reporting currency."""

    def get(self, request):
        on = parse_on(request.query_params.get("on"))
        table = fx.RateTable.load(on)
        payload = {
            "on": on,
            "rates": table.rows(),
            "month_labels": {
                currency: table.month_label(currency) for currency in (fx.USD, fx.EUR)
            },
        }
        return Response(render(payload))
