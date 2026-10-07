from django.urls import path

from apps.employees.views import EmployeeDetailView, EmployeeListView

app_name = "employees"

urlpatterns = [
    path("employees/", EmployeeListView.as_view(), name="list"),
    path("employees/<int:pk>/", EmployeeDetailView.as_view(), name="detail"),
]
