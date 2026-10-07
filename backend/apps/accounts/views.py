"""SimpleJWT login, refresh and logout, plus /auth/me/ (SPEC F8).

Login and refresh are the only unauthenticated API routes. Logout needs the bearer token and
blacklists the refresh token it is given.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.views import TokenBlacklistView, TokenObtainPairView, TokenRefreshView

from apps.accounts.serializers import MeSerializer


class LoginView(TokenObtainPairView):
    """`{email, password}` to `{access, refresh}`, five attempts a minute per client address."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


class RefreshView(TokenRefreshView):
    pass


class LogoutView(TokenBlacklistView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]


class MeView(APIView):
    def get(self, request):
        return Response(MeSerializer(request.user).data)
