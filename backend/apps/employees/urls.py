from django.urls import path

from apps.employees.views import (
    EmployeeAuditView,
    EmployeeDetailView,
    EmployeeExitView,
    EmployeeListCreateView,
)

app_name = "employees"

urlpatterns = [
    path("employees/", EmployeeListCreateView.as_view(), name="list"),
    path("employees/<int:pk>/", EmployeeDetailView.as_view(), name="detail"),
    path("employees/<int:pk>/exit/", EmployeeExitView.as_view(), name="exit"),
    path("employees/<int:pk>/audit/", EmployeeAuditView.as_view(), name="audit"),
]
