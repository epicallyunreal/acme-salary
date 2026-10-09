"""Guard since step 11 (D73): rotate() re-checks the blacklist inside one transaction.

Lead accounts_rotate_not_atomic.

Claim: the refresh endpoint checks the blacklist only when it decodes the token, and rotate() then
blacklists it with SimpleJWT's get_or_create, which does not refuse a token that another request
rotated out in between, so two requests presenting one refresh token together both get a live
session and the reuse rule of SPEC F8 and D21 revokes nothing.
"""

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services

pytestmark = pytest.mark.django_db

REFRESH = "/api/v1/auth/refresh/"


def test_one_token_refreshed_twice_at_once_ends_every_session(anon, hr_user, monkeypatch):
    token = str(RefreshToken.for_user(hr_user))
    other_client = APIClient()
    real_rotate = services.rotate
    completed_first = []

    def other_request_completes_first(refresh):
        # This request has decoded the token and passed the blacklist check. Before it rotates,
        # another client presenting the same token runs to completion on the real rotate().
        monkeypatch.setattr(services, "rotate", real_rotate)
        completed_first.append(other_client.post(REFRESH, {"refresh": token}, format="json"))
        return real_rotate(refresh)

    monkeypatch.setattr(services, "rotate", other_request_completes_first)
    second = anon.post(REFRESH, {"refresh": token}, format="json")

    if [response.status_code for response in completed_first] != [200]:
        pytest.fail("setup: the interleaved refresh did not run once and succeed; update the test")
    live = OutstandingToken.objects.filter(user=hr_user, blacklistedtoken__isnull=True).count()
    assert (second.status_code, live) == (401, 0), (
        f"the request that rotated second answered {second.status_code} and {live} session(s) "
        "stayed live; a token another request rotated out must answer 401 and revoke every "
        "session of its user (SPEC F8, D21)"
    )
