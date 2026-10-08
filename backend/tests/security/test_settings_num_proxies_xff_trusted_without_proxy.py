"""settings_num_proxies_xff_trusted_without_proxy

Claim: the base settings fix DRF ``NUM_PROXIES = 1`` for every deployment mode, so a client that
reaches gunicorn with no proxy in front (``docker compose up`` publishes port 8000 directly)
chooses its own login-throttle bucket through ``X-Forwarded-For`` and never meets the 5-a-minute
limit. The test client plays that client: one directly connected peer, no proxy.

A failure of the final assertion (reported as XFAIL) means six wrong-password logins from that one
peer, each claiming a different ``X-Forwarded-For``, were all answered 401. A pass means the sixth
was throttled with 429, so the header did not choose the bucket, which is the secure behaviour.
"""

import pytest
import rest_framework.throttling  # noqa: F401

# DRF sets ``SimpleRateThrottle.timer = time.time`` when rest_framework.throttling is first
# imported. Run on its own, this file would otherwise import it with the first request, inside the
# autouse freeze in tests/conftest.py, and the throttle would keep freezegun's ``fake_time``, which
# raises TypeError when called as a method. Importing it above, at collection, avoids that.

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/login/"
# RFC 5737 documentation addresses, never routed: the peer from TEST-NET-1, the claims from
# TEST-NET-2.
DIRECT_PEER = "192.0.2.10"
CLAIMED_ADDRESSES = [f"198.51.100.{n}" for n in range(1, 7)]


def attempt(anon, email, claimed):
    return anon.post(
        LOGIN,
        {"email": email, "password": "not-the-password"},
        format="json",
        REMOTE_ADDR=DIRECT_PEER,
        HTTP_X_FORWARDED_FOR=claimed,
    )


def test_with_no_proxy_hop_trusted_the_header_never_chooses_the_bucket(anon, hr_user, settings):
    """Guard since step 11 (D73): compose runs NUM_PROXIES=0, so six attempts from one peer that
    each claim another address share one bucket and the sixth is throttled."""
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 0}

    statuses = [attempt(anon, hr_user.email, claimed).status_code for claimed in CLAIMED_ADDRESSES]

    assert statuses == [401] * 5 + [429]


def test_with_one_hop_trusted_the_last_address_is_the_bucket(anon, hr_user, settings):
    """Fly's value, 1: its proxy appends the client as the last hop, so that address is the
    bucket, and each claimed address here is a client of its own."""
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 1}

    statuses = [attempt(anon, hr_user.email, claimed).status_code for claimed in CLAIMED_ADDRESSES]

    assert statuses == [401] * 6
