"""Session rules without HTTP (SPEC F8, D21): rotation keeps the session's end, reuse revokes."""

import logging
from datetime import datetime

import pytest
from freezegun import freeze_time
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services

pytestmark = pytest.mark.django_db


def epoch(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp())


def test_rotation_keeps_the_session_end(hr_user):
    first = RefreshToken.for_user(hr_user)  # 09:00, so the session ends at 21:00
    assert first["exp"] == epoch("2026-10-07T21:00:00+00:00")

    with freeze_time("2026-10-07T13:00:00Z"):
        access, second = services.rotate(RefreshToken(str(first)))

    assert second["exp"] == first["exp"]
    assert second["iat"] == epoch("2026-10-07T13:00:00+00:00")
    assert second["jti"] != first["jti"]
    assert access["exp"] == epoch("2026-10-07T13:30:00+00:00")
    with pytest.raises(TokenError, match="blacklisted"):
        RefreshToken(str(first))
    assert OutstandingToken.objects.filter(user=hr_user).count() == 2


def test_the_access_token_never_outlives_the_session(hr_user):
    first = RefreshToken.for_user(hr_user)

    with freeze_time("2026-10-07T20:45:00Z"):
        access, second = services.rotate(RefreshToken(str(first)))

    assert access["exp"] == first["exp"] == epoch("2026-10-07T21:00:00+00:00")
    assert second["exp"] == first["exp"]


def test_reuse_of_a_rotated_out_token_revokes_every_session(hr_user, caplog):
    laptop = RefreshToken.for_user(hr_user)
    phone = RefreshToken.for_user(hr_user)
    _, laptop_next = services.rotate(RefreshToken(str(laptop)))

    with caplog.at_level(logging.WARNING, logger="apps.accounts.services"):
        revoked = services.revoke_on_reuse(str(laptop))

    assert revoked == 2
    assert "refresh token reuse for hr@acme.example: revoked 2 live session(s)" in caplog.text
    for token in (laptop_next, phone):
        with pytest.raises(TokenError, match="blacklisted"):
            RefreshToken(str(token))


def test_an_expired_token_that_was_never_rotated_revokes_nothing(hr_user):
    old = RefreshToken.for_user(hr_user)

    with freeze_time("2026-10-08T09:30:00Z"):
        with pytest.raises(TokenError, match="expired"):
            RefreshToken(str(old))
        assert services.revoke_on_reuse(str(old)) == 0

    assert not BlacklistedToken.objects.filter(token__user=hr_user).exists()


def test_an_unknown_string_revokes_nothing_and_revoke_sessions_is_idempotent(hr_user):
    RefreshToken.for_user(hr_user)

    assert services.revoke_on_reuse("not-a-token") == 0
    assert services.revoke_sessions(hr_user) == 1
    assert services.revoke_sessions(hr_user) == 0
