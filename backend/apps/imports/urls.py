from django.urls import path

from apps.imports import views

urlpatterns = [
    path("imports/template/", views.ImportTemplateView.as_view(), name="import-template"),
]
