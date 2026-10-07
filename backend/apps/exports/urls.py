from django.urls import path

from apps.exports import views

urlpatterns = [
    path("exports/employees/", views.ExportEmployeesView.as_view(), name="export-employees"),
    path("exports/insights/<str:name>/", views.ExportInsightView.as_view(), name="export-insight"),
]
