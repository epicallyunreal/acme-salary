"""SimpleJWT login, refresh and logout, plus /auth/me/ (SPEC F8).

Login and refresh are the only unauthenticated API routes. Logout needs the bearer token and
blacklists the refresh token it is given.
"""

import ipaddress

from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView

from apps.accounts.serializers import MeSerializer


class LoginRateThrottle(ScopedRateThrottle):
    """The login bucket is keyed on the client address, with an IPv6 address reduced to its /64:
    a client controls at least that much and could otherwise mint a fresh bucket per request.
    An IPv4-mapped address (`::ffff:a.b.c.d`) is the IPv4 client it wraps, so it is unmapped
    first: every mapped client would otherwise fold into the one `::/64` bucket (D73)."""

    def get_ident(self, request):
        ident = super().get_ident(request)
        try:
            address = ipaddress.ip_address(ident)
        except ValueError:
            return ident
        if address.version == 6 and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        if address.version == 6:
            return str(ipaddress.ip_network(f"{address}/64", strict=False))
        return str(address)


class LoginView(TokenObtainPairView):
    """`{email, password}` to `{access, refresh}`, five attempts a minute per client address."""

    throttle_classes = [LoginRateThrottle]
    throttle_scope = "login"


class RefreshView(TokenRefreshView):
    """`{refresh}` to a new pair, JSON only and thirty a minute per client address (D73)."""

    throttle_classes = [LoginRateThrottle]
    throttle_scope = "refresh"
    parser_classes = [JSONParser]


class LogoutView(TokenBlacklistView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]


class MeView(APIView):
    def get(self, request):
        return Response(MeSerializer(request.user).data)
