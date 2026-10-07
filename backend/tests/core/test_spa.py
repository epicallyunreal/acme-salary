import pytest

INDEX_HTML = "<!doctype html><title>ACME Salary</title>"


@pytest.fixture
def bundle(settings, tmp_path):
    (tmp_path / "index.html").write_text(INDEX_HTML)
    settings.SPA_DIR = str(tmp_path)
    return tmp_path


def test_the_served_index_carries_the_security_policy(client, bundle):
    from tests.core.test_security_headers import EXPECTED, directives

    response = client.get("/employees/12")

    assert response.status_code == 200
    assert directives(response) == EXPECTED
    assert "Cache-Control" not in response or "no-store" not in response["Cache-Control"]


def test_catch_all_is_404_without_a_bundle(client):
    assert client.get("/employees/12").status_code == 404


def test_catch_all_is_404_when_the_bundle_has_no_index(client, settings, tmp_path):
    settings.SPA_DIR = str(tmp_path)

    assert client.get("/employees/12").status_code == 404


def test_catch_all_serves_index_html_for_client_routes(client, bundle):
    response = client.get("/employees/12")

    assert response.status_code == 200
    assert b"ACME Salary" in response.content
    assert response["Content-Type"] == "text/html; charset=utf-8"
    assert response["Cache-Control"] == "max-age=60, public"


def test_catch_all_only_answers_safe_methods(client, bundle):
    response = client.post("/employees/12")

    assert response.status_code == 405
    assert response["Allow"] == "GET, HEAD"


@pytest.mark.parametrize("path", ["/api/v1/nothing/", "/assets/missing.js"])
def test_api_and_asset_paths_are_not_caught(client, bundle, path):
    response = client.get(path)

    assert response.status_code == 404
    assert b"ACME Salary" not in response.content


@pytest.mark.django_db
def test_healthz_wins_over_the_catch_all(client, bundle):
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
