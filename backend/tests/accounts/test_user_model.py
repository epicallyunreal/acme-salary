import pytest
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError

User = get_user_model()

pytestmark = pytest.mark.django_db


def test_email_is_the_login_name_and_there_is_no_username():
    assert User.USERNAME_FIELD == "email"
    assert User.REQUIRED_FIELDS == []
    assert "username" not in {field.name for field in User._meta.get_fields()}


def test_create_user_lowercases_the_email_and_hashes_the_password():
    user = User.objects.create_user("HR@ACME.example", "correct-horse-battery")

    assert user.email == "hr@acme.example"
    assert user.password != "correct-horse-battery"
    assert user.check_password("correct-horse-battery")
    assert authenticate(email="hr@acme.example", password="correct-horse-battery") == user
    assert authenticate(email="hr@acme.example", password="wrong") is None


def test_create_user_requires_an_email():
    with pytest.raises(ValueError, match="email"):
        User.objects.create_user("", "correct-horse-battery")


def test_email_is_unique():
    User.objects.create_user("hr@acme.example", "correct-horse-battery")
    with pytest.raises(IntegrityError):
        User.objects.create_user("hr@acme.example", "another-password")


def test_factory_builds_a_user_who_can_log_in(hr_user):
    assert hr_user.email == "hr@acme.example"
    assert hr_user.check_password("correct-horse-battery")
