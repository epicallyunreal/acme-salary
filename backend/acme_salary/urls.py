"""URL root: the API under /api/v1/, /healthz at the site root, the SPA for everything else."""

from django.urls import include, path, re_path

from acme_salary.spa import spa_index
from apps.core.views import healthz

# Each app's urls.py is appended here in the step that builds it.
api_v1_patterns = [
    path("", include("apps.accounts.urls")),
]

urlpatterns = [
    path("api/v1/", include(api_v1_patterns)),
    path("healthz", healthz, name="healthz"),
    re_path(r"^(?!api/|assets/|healthz$).*$", spa_index, name="spa"),
]
