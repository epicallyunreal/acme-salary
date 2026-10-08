from rest_framework import serializers


class ResetSerializer(serializers.Serializer):
    """Shape only: the service checks the password and the confirmation, so a blank or a wrong
    value is its 403 naming the field, never a 400 (SPEC section 8)."""

    password = serializers.CharField(allow_blank=True, max_length=256, trim_whitespace=False)
    confirm = serializers.CharField(allow_blank=True)
