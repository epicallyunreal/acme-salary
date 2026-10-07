def test_catch_all_is_404_without_a_bundle(client):
    assert client.get("/employees/12").status_code == 404


def test_catch_all_serves_index_html_for_client_routes(client, settings, tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>ACME Salary</title>")
    settings.SPA_DIR = str(tmp_path)

    response = client.get("/employees/12")

    assert response.status_code == 200
    assert b"ACME Salary" in response.content
    assert response["Content-Type"] == "text/html; charset=utf-8"
    assert response["Cache-Control"] == "max-age=60, public"


def test_api_and_asset_paths_are_not_caught(client, settings, tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>ACME Salary</title>")
    settings.SPA_DIR = str(tmp_path)

    for path in ("/api/v1/nothing/", "/assets/missing.js"):
        response = client.get(path)
        assert response.status_code == 404
        assert b"ACME Salary" not in response.content
