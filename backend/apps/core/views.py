from django.contrib.auth import get_user_model
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    """Unauthenticated liveness check for Fly: one query proves the database answers.

    A plain Django view, so DRF's default IsAuthenticated does not apply (SPEC section 8).
    """
    get_user_model().objects.order_by().exists()
    return JsonResponse({"status": "ok"})
