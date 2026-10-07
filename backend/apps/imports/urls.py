from django.urls import path

from apps.imports import views

urlpatterns = [
    path("imports/", views.ImportListCreateView.as_view(), name="import-list"),
    path("imports/template/", views.ImportTemplateView.as_view(), name="import-template"),
    path("imports/<int:pk>/", views.ImportDetailView.as_view(), name="import-detail"),
    path("imports/<int:pk>/rows/", views.ImportRowListView.as_view(), name="import-rows"),
    path(
        "imports/<int:pk>/rows/<int:row_pk>/skip/",
        views.ImportRowSkipView.as_view(),
        name="import-row-skip",
    ),
    path(
        "imports/<int:pk>/rows/<int:row_pk>/unskip/",
        views.ImportRowUnskipView.as_view(),
        name="import-row-unskip",
    ),
    path("imports/<int:pk>/approve/", views.ImportApproveView.as_view(), name="import-approve"),
    path("imports/<int:pk>/discard/", views.ImportDiscardView.as_view(), name="import-discard"),
]
