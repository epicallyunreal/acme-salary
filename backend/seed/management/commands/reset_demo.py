"""`reset_demo`: rebuild the demo database with the fixed arguments, keeping users (SPEC F8)."""

from django.core.management.base import BaseCommand

from seed import profiles
from seed.management.commands.seed_data import seed


class Command(BaseCommand):
    help = (
        "Truncate the business tables and reseed 10,000 active and 5,000 exited employees with "
        "seed 42. Users are kept."
    )

    def handle(self, *args, **options):
        elapsed = seed(
            profiles.ACTIVE_EMPLOYEES, profiles.EXITED_EMPLOYEES, 42, reset=True, stdout=self.stdout
        )
        self.stdout.write(f"demo reset in {elapsed:.1f} s")
