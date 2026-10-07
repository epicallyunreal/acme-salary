from django.urls import path

from apps.insights import views

urlpatterns = [
    path("insights/<str:name>/", views.InsightView.as_view(), name="insight"),
]
