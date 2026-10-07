import pytest


@pytest.mark.django_db
def test_healthz_is_public_and_makes_one_query(client, django_assert_num_queries):
    with django_assert_num_queries(1):
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_only_answers_get(client):
    assert client.post("/healthz").status_code == 405
