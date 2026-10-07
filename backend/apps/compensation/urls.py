from django.urls import path

from apps.compensation.views import CompensationHistoryView, CompensationRecordView

app_name = "compensation"

urlpatterns = [
    path("employees/<int:pk>/compensation/", CompensationHistoryView.as_view(), name="history"),
    path("compensation/<int:pk>/", CompensationRecordView.as_view(), name="record"),
]
