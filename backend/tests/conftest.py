import pytest

from tests.factories import UserFactory


@pytest.fixture
def hr_user(db):
    return UserFactory(email="hr@acme.example")
