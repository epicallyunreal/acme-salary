"""accounts_password_change_keeps_refresh_token_valid

Claim: changing the HR Manager's password (`manage.py changepassword` is set_password, then
save) ends no session. A refresh token issued before the change still rotates at
/api/v1/auth/refresh/ into an access token that opens the API, until the session's 12-hour end.

The test asserts the secure behaviour: after the change, the old refresh token is refused, or
the access token it mints is refused at /api/v1/auth/me/. An assertion failure (XFAIL under the
marker) means the weakness is present. XPASS, reported as a strict failure, means it did not
reproduce or has been fixed. A pytest.fail from a setup or outcome check is a plain failure,
never read as the weakness.
"""

import pytest

# Load DRF's throttle module at collection, outside the autouse freeze_time:
# SimpleRateThrottle.timer = time.time is bound on first import, and under freezegun
# that would be fake_time, which fails when the login throttle calls it as a method.
import rest_framework.throttling  # noqa: F401
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

REVIEW = "docs/reviews/security-audit-2026-10-08.md"

LOGIN = "/api/v1/auth/login/"
REFRESH = "/api/v1/auth/refresh/"
ME = "/api/v1/auth/me/"
OLD_PASSWORD = "correct-horse-battery"  # the dummy password of tests.factories.UserFactory
NEW_PASSWORD = "rotated-lantern-staple-42"  # a dummy, never a real credential


def me_status(access: str) -> int:
    """The status /auth/me/ answers for a bearer access token; a server error is a 500."""
    client = APIClient()
    client.raise_request_exception = False
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client.get(ME).status_code


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason=(
        "accounts_password_change_keeps_refresh_token_valid: accepted in "
        f"{REVIEW}: the operator rotates the HR password with changepassword and then "
        "revoke_sessions (README), so no session outlives the change. XFAIL means the "
        "behaviour is as accepted; XPASS (a strict failure) means it changed, so revisit the "
        "review."
    ),
)
def test_a_password_change_ends_the_session_of_an_earlier_refresh_token(anon, hr_user):
    anon.raise_request_exception = False
    credentials = {"email": "hr@acme.example", "password": OLD_PASSWORD}
    login = anon.post(LOGIN, credentials, format="json")
    if login.status_code != 200 or me_status(login.json()["access"]) != 200:
        pytest.fail(f"setup: the login opened no session (status {login.status_code})")
    old_refresh = login.json()["refresh"]

    # What `manage.py changepassword` does in Django 6.1: set_password, then save.
    hr_user.set_password(NEW_PASSWORD)
    hr_user.save()

    refreshed = anon.post(REFRESH, {"refresh": old_refresh}, format="json")
    me = me_status(refreshed.json()["access"]) if refreshed.status_code == 200 else None
    outcome = (refreshed.status_code, me)
    if outcome not in {(200, 200), (200, 401), (401, None)}:
        pytest.fail(f"unexpected outcome (refresh, me) = {outcome}: {refreshed.content!r}")

    assert outcome != (200, 200), "the pre-change refresh token still opens the API"
