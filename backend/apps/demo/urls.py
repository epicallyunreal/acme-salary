from django.urls import path

from apps.demo import views

app_name = "demo"

urlpatterns = [
    path("admin/reset-demo/", views.ResetDemoView.as_view(), name="reset-demo"),
    path("admin/sample-files/", views.SampleFileListView.as_view(), name="sample-files"),
    path("admin/sample-files/<slug:name>/", views.SampleFileView.as_view(), name="sample-file"),
]
