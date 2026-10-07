import pytest
from django.contrib.auth import authenticate, get_user_model
from django.db import IntegrityError

User = get_user_model()

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery"


def test_email_is_the_login_name_and_there_is_no_username():
    assert User.USERNAME_FIELD == "email"
    assert User.REQUIRED_FIELDS == []
    assert "username" not in {field.name for field in User._meta.get_fields()}


def test_create_user_lowercases_the_email():
    user = User.objects.create_user("HR@ACME.example", PASSWORD)

    assert user.email == "hr@acme.example"


def test_create_user_hashes_the_password():
    user = User.objects.create_user("hr@acme.example", PASSWORD)

    assert user.password != PASSWORD
    assert user.check_password(PASSWORD)


def test_create_user_is_neither_staff_nor_superuser():
    user = User.objects.create_user("hr@acme.example", PASSWORD)

    assert (user.is_staff, user.is_superuser) == (False, False)


def test_create_superuser_sets_both_flags():
    user = User.objects.create_superuser("root@acme.example", PASSWORD)

    assert (user.is_staff, user.is_superuser) == (True, True)


def test_authenticate_accepts_the_password():
    user = User.objects.create_user("hr@acme.example", PASSWORD)

    assert authenticate(email="hr@acme.example", password=PASSWORD) == user


def test_authenticate_rejects_a_wrong_password():
    User.objects.create_user("hr@acme.example", PASSWORD)

    assert authenticate(email="hr@acme.example", password="wrong") is None


def test_create_user_requires_an_email():
    with pytest.raises(ValueError, match="email"):
        User.objects.create_user("", PASSWORD)


def test_email_is_unique_regardless_of_case():
    User.objects.create_user("hr@acme.example", PASSWORD)

    with pytest.raises(IntegrityError):
        User.objects.create_user("HR@ACME.example", "another-password")


def test_factory_builds_a_user_who_can_log_in(hr_user):
    assert hr_user.email == "hr@acme.example"
    assert hr_user.check_password(PASSWORD)
