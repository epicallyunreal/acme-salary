"""Guard since step 11 (D73): LoginRateThrottle unmaps an IPv4-mapped address first.

accounts_login_throttle_ipv4_mapped_collapse

Claim: LoginRateThrottle.get_ident folds every IPv6 ident to its /64 without first unwrapping
IPv4-mapped addresses, so every "::ffff:a.b.c.d" client is keyed on the one string "::/64" and
unrelated IPv4 clients share a single 5/min login bucket.

The test asserts the secure behaviour: after one IPv4-mapped client has spent its five attempts,
an unrelated IPv4-mapped client still gets its own first attempt (401 for a wrong password),
never 429. A failure (XFAIL) means the collapse is present in the throttle code. A dotted-quad
control runs first, so a throttle that is not keyed on the X-Forwarded-For hop in this
environment is reported as an ordinary failure through pytest.fail, never as an XFAIL.
"""

import pytest

# Loaded at collection, before the autouse freeze_time in tests/conftest.py starts. DRF binds
# SimpleRateThrottle.timer = time.time when rest_framework.throttling is first imported, and only
# apps.accounts.views imports it. Run alone, this file would otherwise load it on its first
# request inside the freeze, keep freezegun's fake_time as a method, and every login would raise
# TypeError. The full suite loads the URLconf at collection through tests/test_auth_coverage.py.
import apps.accounts.views  # noqa: F401

pytestmark = pytest.mark.django_db

LOGIN = "/api/v1/auth/login/"

# Four unrelated IPv4 clients, each in a different /24: two written as dotted quads for the
# control, two written as IPv4-mapped IPv6 literals for the claim. Distinct /24s keep the control
# and the claim in separate buckets after a fix that unwraps mapped addresses.
CONTROL_SPENDER = "192.0.2.7"
CONTROL_OTHER = "198.51.100.7"
MAPPED_SPENDER = "::ffff:203.0.113.7"
MAPPED_OTHER = "::ffff:198.18.0.7"


def attempt(client, address, email):
    """A wrong-password login; NUM_PROXIES is 1, so the last X-Forwarded-For hop is the client."""
    return client.post(
        LOGIN,
        {"email": email, "password": "wrong"},
        format="json",
        HTTP_X_FORWARDED_FOR=address,
    )


def spend_the_bucket(client, address, email):
    """Five wrong-password logins from one client, each answered 401, fill its 5/min bucket."""
    for n in range(1, 6):
        status = attempt(client, address, email).status_code
        if status != 401:
            pytest.fail(f"setup: attempt {n} from {address} gave {status}, expected 401")


def test_unrelated_ipv4_mapped_clients_do_not_share_a_login_bucket(anon, hr_user):
    # Control: written as dotted quads, the two clients have separate buckets.
    spend_the_bucket(anon, CONTROL_SPENDER, hr_user.email)
    control = attempt(anon, CONTROL_OTHER, hr_user.email).status_code
    if control != 401:
        pytest.fail(
            f"setup: {CONTROL_OTHER} gave {control} after {CONTROL_SPENDER} spent its bucket, "
            "so the throttle here is not keyed on the X-Forwarded-For hop"
        )

    # The claim: two unrelated clients written as IPv4-mapped IPv6 literals.
    spend_the_bucket(anon, MAPPED_SPENDER, hr_user.email)
    response = attempt(anon, MAPPED_OTHER, hr_user.email)
    if response.status_code not in (401, 429):
        pytest.fail(f"setup: {MAPPED_OTHER} gave {response.status_code}, expected 401 or 429")

    assert response.status_code == 401, (
        f"{MAPPED_OTHER} was throttled with 429 after {MAPPED_SPENDER} spent five attempts: "
        "both IPv4-mapped idents fold to the shared ::/64 login bucket"
    )
