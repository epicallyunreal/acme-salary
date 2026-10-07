"""The production settings module refuses to boot on missing or placeholder secrets."""

import importlib

import pytest
from django.core.exceptions import ImproperlyConfigured

GOOD_ENV = {
    "SECRET_KEY": "a-long-random-looking-test-key-" * 3,
    "ALLOWED_HOSTS": "acme.nutanprabhat.dev",
    "SEED_ADMIN_PASSWORD": "a-real-password-13",
    "DATABASE_PATH": "/tmp/acme-prod-settings-test.sqlite3",
}


def load_prod(monkeypatch, **overrides):
    for name in ("SECRET_KEY", "ALLOWED_HOSTS", "SEED_ADMIN_PASSWORD", "DEBUG", "SPA_DIR"):
        monkeypatch.delenv(name, raising=False)
    for name, value in {**GOOD_ENV, **overrides}.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    # prod does `from .base import *`, so base must re-read the environment first.
    importlib.reload(importlib.import_module("acme_salary.settings.base"))
    return importlib.reload(importlib.import_module("acme_salary.settings.prod"))


def test_prod_settings_load_with_real_values(monkeypatch):
    prod = load_prod(monkeypatch)

    assert prod.DEBUG is False
    assert prod.ALLOWED_HOSTS == ["acme.nutanprabhat.dev"]
    assert prod.WHITENOISE_ROOT == "/app/spa"
    assert prod.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")


@pytest.mark.parametrize("missing", ["SECRET_KEY", "ALLOWED_HOSTS", "SEED_ADMIN_PASSWORD"])
def test_prod_settings_require_each_secret(monkeypatch, missing):
    with pytest.raises(ImproperlyConfigured, match=missing):
        load_prod(monkeypatch, **{missing: None})


@pytest.mark.parametrize(
    "secret_key",
    ["replace-with-a-long-random-string", "dev-only-insecure-key-do-not-deploy", "short", "a" * 60],
)
def test_prod_settings_reject_placeholder_or_weak_secret_key(monkeypatch, secret_key):
    with pytest.raises(ImproperlyConfigured, match="SECRET_KEY"):
        load_prod(monkeypatch, SECRET_KEY=secret_key)


def test_prod_settings_reject_the_example_admin_password(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="SEED_ADMIN_PASSWORD"):
        load_prod(monkeypatch, SEED_ADMIN_PASSWORD="change-me")
