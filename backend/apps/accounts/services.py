"""Session rules (SPEC F8, D21): a session ends 12 hours after login however often it refreshes,
and a refresh token presented after it was rotated out or logged out revokes every session of
its user (RFC 9700 section 4.14). Plain functions over SimpleJWT's tokens, tested without HTTP.
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.utils import get_md5_hash_password

logger = logging.getLogger(__name__)


def rotate(refresh: RefreshToken) -> tuple[AccessToken, RefreshToken]:
    """Blacklists the presented token and issues a new pair. The new refresh token keeps the
    session's original `exp`, so rotation never extends a session, and the access token's `exp`
    never passes it.

    One transaction, which SQLite opens for writing at once (section 13), and the presented
    token's row is checked for a blacklist entry again inside it: two presentations of one
    token together cannot both succeed, the second finds the first's entry and raises as a
    reused token does, which the serializer turns into the revoke-all (D73)."""
    session_end = refresh.payload["exp"]
    with transaction.atomic():
        jti = refresh.payload[api_settings.JTI_CLAIM]
        if BlacklistedToken.objects.filter(token__jti=jti).exists():
            raise TokenError("Token is blacklisted")
        access = refresh.access_token
        if access.payload["exp"] > session_end:
            access.payload["exp"] = session_end
        refresh.blacklist()
        refresh.set_jti()
        refresh.set_iat()
        refresh.payload["exp"] = session_end
        refresh.outstand()
    return access, refresh


def refresh_session(raw_token: str) -> tuple[AccessToken, RefreshToken]:
    """`{refresh}` to a new pair under the session rules (F8, D21, D73): the token must decode
    and belong to an active user, and `rotate` must find it unused. A token that fails to decode
    or that another request rotated meanwhile is a reuse, so every session of its user ends
    before the error goes back. The one place the rule lives; the serializer only calls it."""
    try:
        refresh = RefreshToken(raw_token)
        user_id = refresh.payload.get(api_settings.USER_ID_CLAIM)
        user = (
            get_user_model().objects.filter(**{api_settings.USER_ID_FIELD: user_id}).first()
            if user_id
            else None
        )
        if user is None or not api_settings.USER_AUTHENTICATION_RULE(user):
            raise AuthenticationFailed(
                "No active account found with the given credentials", "no_active_account"
            )
        # A token issued before a password change ends here, rather than rotating into access
        # tokens that are each refused (D76).
        if api_settings.CHECK_REVOKE_TOKEN and refresh.payload.get(
            api_settings.REVOKE_TOKEN_CLAIM
        ) != get_md5_hash_password(user.password):
            raise AuthenticationFailed("The user's password has been changed.", "password_changed")
        return rotate(refresh)
    except TokenError:
        revoke_on_reuse(raw_token)
        raise


def revoke_sessions(user) -> int:
    """Blacklists every outstanding refresh token of the user. Returns how many were still live."""
    live = OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True)
    count = 0
    for outstanding in live:
        BlacklistedToken.objects.get_or_create(token=outstanding)
        count += 1
    return count


def revoke_on_reuse(raw_token: str) -> int:
    """A token string that matches a blacklisted `OutstandingToken` row was rotated out or
    logged out and is being presented again, so every session of that row's user ends. The
    user comes from the row, never from the unverified payload. An unknown string, or a token
    that merely expired without ever being rotated, revokes nothing."""
    reused = (
        OutstandingToken.objects.filter(token=raw_token, blacklistedtoken__isnull=False)
        .select_related("user")
        .first()
    )
    if reused is None or reused.user is None:
        return 0
    count = revoke_sessions(reused.user)
    logger.warning(
        "refresh token reuse for %s: revoked %d live session(s)", reused.user.email, count
    )
    return count
