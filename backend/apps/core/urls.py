from django.urls import path

from apps.core.views import ComponentListView, CountryListView, DepartmentListView, ExchangeRateView

app_name = "core"

urlpatterns = [
    path("meta/countries/", CountryListView.as_view(), name="countries"),
    path("meta/departments/", DepartmentListView.as_view(), name="departments"),
    path("meta/components/", ComponentListView.as_view(), name="components"),
    path("meta/exchange-rates/", ExchangeRateView.as_view(), name="exchange-rates"),
]
