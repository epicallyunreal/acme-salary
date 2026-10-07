from django.urls import path

from apps.imports import views

urlpatterns = [
    path("imports/", views.ImportListCreateView.as_view(), name="import-list"),
    path("imports/template/", views.ImportTemplateView.as_view(), name="import-template"),
    path("imports/<int:pk>/", views.ImportDetailView.as_view(), name="import-detail"),
    path("imports/<int:pk>/rows/", views.ImportRowListView.as_view(), name="import-rows"),
]
