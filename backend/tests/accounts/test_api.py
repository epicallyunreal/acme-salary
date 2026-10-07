"""SPEC F8: login, rotation, logout, the throttle and /auth/me/."""

import pytest

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery"


def login(client, email="hr@acme.example", password=PASSWORD):
    return client.post("/api/v1/auth/login/", {"email": email, "password": password}, format="json")


def test_login_returns_an_access_and_a_refresh_token(anon, hr_user):
    response = login(anon)

    assert response.status_code == 200
    assert set(response.json()) == {"access", "refresh"}


def test_login_with_a_wrong_password_is_401(anon, hr_user):
    response = login(anon, password="wrong")

    assert response.status_code == 401
    assert "detail" in response.json()


def test_the_sixth_login_attempt_within_a_minute_is_429(anon, hr_user):
    for _ in range(5):
        assert login(anon, password="wrong").status_code == 401

    response = login(anon)

    assert response.status_code == 429
    assert "Retry-After" in response


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
