"""`revoke_sessions <email>`: end every session of a user now, without rotating SECRET_KEY."""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts import services


class Command(BaseCommand):
    help = "Blacklist every refresh token of the user, so each of their sessions ends now."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(email__iexact=options["email"]).first()
        if user is None:
            raise CommandError(f"no user with the email {options['email']}")
        count = services.revoke_sessions(user)
        self.stdout.write(f"revoked {count} live session(s) for {user.email}")
