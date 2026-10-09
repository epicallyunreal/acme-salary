"""SPEC F8: login, rotation, logout, the throttle, the session rules and /auth/me/."""

import logging
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from freezegun import freeze_time
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery"
REFRESH = "/api/v1/auth/refresh/"
LOGOUT = "/api/v1/auth/logout/"


def refresh(client, token):
    return client.post(REFRESH, {"refresh": token}, format="json")


def login(client, email="hr@acme.example", password=PASSWORD):
    return client.post("/api/v1/auth/login/", {"email": email, "password": password}, format="json")


def test_login_returns_an_access_and_a_refresh_token(anon, hr_user):
    response = login(anon)

    assert response.status_code == 200
    assert set(response.json()) == {"access", "refresh"}


def me(client, access):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    status = client.get("/api/v1/auth/me/").status_code
    client.credentials()
    return status


def test_a_password_change_ends_every_earlier_session_and_a_fresh_login_works(anon, hr_user):
    """SimpleJWT's revoke claim (D76): what `changepassword` does, set_password then save, ends
    the earlier access token and whatever its refresh token rotates into."""
    before = login(anon).json()

    hr_user.set_password("rotated-lantern-staple-42")  # a dummy, never a real credential
    hr_user.save()

    assert me(anon, before["access"]) == 401
    rotated = refresh(anon, before["refresh"])
    assert rotated.status_code == 200
    assert me(anon, rotated.json()["access"]) == 401
    fresh = login(anon, password="rotated-lantern-staple-42")
    assert fresh.status_code == 200
    assert me(anon, fresh.json()["access"]) == 200


def test_login_with_a_wrong_password_is_401(anon, hr_user):
    response = login(anon, password="wrong")

    assert response.status_code == 401
    assert response.json() == {"detail": "No active account found with the given credentials"}


def test_the_sixth_login_attempt_within_a_minute_is_429(anon, hr_user):
    for _ in range(5):
        assert login(anon, password="wrong").status_code == 401

    response = login(anon)

    assert response.status_code == 429
    assert "Retry-After" in response


def test_the_login_throttle_counts_an_ipv6_client_by_its_64_bit_prefix(anon, hr_user):
    """NUM_PROXIES is 1, so the client address is the last hop in X-Forwarded-For."""

    def attempt(address):
        return anon.post(
            "/api/v1/auth/login/",
            {"email": hr_user.email, "password": "wrong"},
            format="json",
            HTTP_X_FORWARDED_FOR=address,
        )

    for n in range(5):
        assert attempt(f"2a09:8280:1::1aa:467d:{n + 1}").status_code == 401

    assert attempt("2a09:8280:1::1aa:467d:ffff").status_code == 429
    assert attempt("2a09:8280:2::1").status_code == 401


def test_the_access_token_opens_me_and_nothing_else_does(anon, api, hr_user):
    assert anon.get("/api/v1/auth/me/").status_code == 401

    response = api.get("/api/v1/auth/me/")

    assert response.status_code == 200
    assert response.json() == {"id": hr_user.pk, "email": "hr@acme.example"}


def test_refresh_rotates_and_the_old_refresh_token_is_rejected(anon, hr_user):
    first = login(anon).json()

    rotated = anon.post("/api/v1/auth/refresh/", {"refresh": first["refresh"]}, format="json")
    assert rotated.status_code == 200
    assert set(rotated.json()) == {"access", "refresh"}
    assert rotated.json()["refresh"] != first["refresh"]

    reused = anon.post("/api/v1/auth/refresh/", {"refresh": first["refresh"]}, format="json")
    assert reused.status_code == 401
    assert reused.json()["detail"] == "Token is blacklisted"


def test_logout_blacklists_the_refresh_token(anon, hr_user):
    tokens = login(anon).json()
    anon.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    response = anon.post("/api/v1/auth/logout/", {"refresh": tokens["refresh"]}, format="json")
    assert response.status_code == 200

    anon.credentials()
    reused = anon.post("/api/v1/auth/refresh/", {"refresh": tokens["refresh"]}, format="json")
    assert reused.status_code == 401


def test_logout_needs_the_bearer_token(anon, hr_user):
    tokens = login(anon).json()

    response = anon.post("/api/v1/auth/logout/", {"refresh": tokens["refresh"]}, format="json")

    assert response.status_code == 401


def test_refresh_keeps_the_session_end_and_caps_the_access_token(anon, hr_user):
    first = login(anon).json()  # 09:00, so the session ends at 21:00
    session_end = RefreshToken(first["refresh"])["exp"]

    with freeze_time("2026-10-07T20:45:00Z"):  # decoded here too: the new iat is 20:45
        rotated = refresh(anon, first["refresh"]).json()
        assert RefreshToken(rotated["refresh"])["exp"] == session_end
        assert AccessToken(rotated["access"])["exp"] == session_end


def test_a_reused_refresh_token_ends_every_session(anon, hr_user, caplog):
    laptop = login(anon).json()
    phone = login(anon).json()
    rotated = refresh(anon, laptop["refresh"]).json()

    with caplog.at_level(logging.WARNING, logger="apps.accounts.services"):
        reused = refresh(anon, laptop["refresh"])

    assert reused.status_code == 401
    assert reused.json()["detail"] == "Token is blacklisted"
    assert "revoked 2 live session(s)" in caplog.text
    assert refresh(anon, rotated["refresh"]).status_code == 401
    assert refresh(anon, phone["refresh"]).status_code == 401


def test_a_token_presented_after_logout_ends_every_session(anon, hr_user):
    laptop = login(anon).json()
    phone = login(anon).json()
    anon.credentials(HTTP_AUTHORIZATION=f"Bearer {laptop['access']}")
    assert anon.post(LOGOUT, {"refresh": laptop["refresh"]}, format="json").status_code == 200
    anon.credentials()

    assert refresh(anon, laptop["refresh"]).status_code == 401

    assert refresh(anon, phone["refresh"]).status_code == 401


def test_an_expired_token_that_was_never_rotated_revokes_nothing(anon, hr_user):
    old = login(anon).json()

    with freeze_time("2026-10-07T22:00:00Z"):  # the 09:00 session ended at 21:00
        fresh = login(anon).json()
        expired = refresh(anon, old["refresh"])
        assert expired.status_code == 401
        assert "expired" in expired.json()["detail"]
        assert refresh(anon, fresh["refresh"]).status_code == 200


def test_revoke_sessions_command_ends_every_session(anon, hr_user):
    laptop = login(anon).json()
    phone = login(anon).json()
    out = StringIO()

    call_command("revoke_sessions", "HR@acme.example", stdout=out)

    assert out.getvalue().strip() == "revoked 2 live session(s) for hr@acme.example"
    assert refresh(anon, laptop["refresh"]).status_code == 401
    assert refresh(anon, phone["refresh"]).status_code == 401
    with pytest.raises(CommandError, match="no user with the email nobody@acme.example"):
        call_command("revoke_sessions", "nobody@acme.example")


def test_the_refresh_endpoint_takes_json_only(anon, hr_user):
    """D73: a multipart body is refused before the token is read."""
    token = str(RefreshToken.for_user(hr_user))

    response = anon.post(REFRESH, {"refresh": token}, format="multipart")

    assert response.status_code == 415
    assert response.json()["detail"].startswith("Unsupported media type")


def test_the_refresh_endpoint_is_throttled_per_client_address(anon, hr_user):
    """D73: thirty a minute, keyed on the client address as the login is."""
    for _ in range(30):
        assert refresh(anon, "not-a-token").status_code == 401

    assert refresh(anon, "not-a-token").status_code == 429
    elsewhere = anon.post(
        REFRESH, {"refresh": "not-a-token"}, format="json", HTTP_X_FORWARDED_FOR="203.0.113.9"
    )
    assert elsewhere.status_code == 401


def test_an_ipv4_mapped_address_is_the_ipv4_client_it_wraps(anon, hr_user):
    """D73: `::ffff:a.b.c.d` buckets with `a.b.c.d`, not with every other mapped client."""

    def attempt(address):
        return anon.post(
            "/api/v1/auth/login/",
            {"email": hr_user.email, "password": "wrong"},
            format="json",
            HTTP_X_FORWARDED_FOR=address,
        )

    for n in range(5):
        assert attempt("::ffff:203.0.113.7" if n % 2 else "203.0.113.7").status_code == 401

    assert attempt("::ffff:203.0.113.7").status_code == 429
    assert attempt("::ffff:203.0.113.8").status_code == 401
