"""The session rules of `accounts/services.py` without HTTP (F8, D21, D73)."""

import pytest
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services

pytestmark = pytest.mark.django_db


def live_sessions(user) -> int:
    return OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True).count()


def test_refresh_session_rotates_a_live_token_and_keeps_the_session_end(hr_user):
    first = RefreshToken.for_user(hr_user)

    access, second = services.refresh_session(str(first))

    assert second.payload["exp"] == first.payload["exp"]
    assert access.payload["exp"] <= first.payload["exp"]
    assert BlacklistedToken.objects.filter(token__jti=first["jti"]).exists()
    assert live_sessions(hr_user) == 1


def test_rotate_refuses_a_token_another_request_rotated_meanwhile(hr_user):
    """The re-check inside the transaction: one token, decoded twice, rotated twice."""
    token = RefreshToken.for_user(hr_user)
    presented_twice = RefreshToken(str(token))
    services.rotate(token)
    before = OutstandingToken.objects.count()

    with pytest.raises(TokenError, match="blacklisted"):
        services.rotate(presented_twice)

    assert OutstandingToken.objects.count() == before


def test_refresh_session_treats_a_rotated_out_token_as_a_reuse_and_revokes_every_session(
    hr_user,
):
    stale = str(RefreshToken.for_user(hr_user))
    services.refresh_session(stale)
    RefreshToken.for_user(hr_user)  # a second live session
    assert live_sessions(hr_user) == 2

    with pytest.raises(TokenError):
        services.refresh_session(stale)

    assert live_sessions(hr_user) == 0


def test_refresh_session_refuses_a_token_whose_user_is_inactive_or_gone(hr_user):
    token = str(RefreshToken.for_user(hr_user))
    hr_user.is_active = False
    hr_user.save(update_fields=["is_active"])

    with pytest.raises(AuthenticationFailed, match="No active account"):
        services.refresh_session(token)

    hr_user.delete()
    with pytest.raises(AuthenticationFailed, match="No active account"):
        services.refresh_session(token)


def test_a_string_that_is_no_token_revokes_nothing(hr_user):
    RefreshToken.for_user(hr_user)

    with pytest.raises(TokenError):
        services.refresh_session("not-a-token")

    assert live_sessions(hr_user) == 1
