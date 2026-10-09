"""The session rules of `accounts/services.py` without HTTP (F8, D21, D73)."""

import pytest
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.utils import get_md5_hash_password

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


def test_rotate_carries_the_revoke_claim_to_both_new_tokens(hr_user):
    """A password change ends an earlier session only if every token carries a hash of the
    password, the new refresh token and the access token rotation mints included (D76)."""
    access, rotated = services.rotate(RefreshToken(str(RefreshToken.for_user(hr_user))))

    expected = get_md5_hash_password(hr_user.password)
    assert rotated.payload[api_settings.REVOKE_TOKEN_CLAIM] == expected
    assert access.payload[api_settings.REVOKE_TOKEN_CLAIM] == expected
