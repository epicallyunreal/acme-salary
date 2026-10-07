"""`set_exchange_rate FROM TO RATE --effective-from YYYY-MM-01 [--replace]`.

SPEC section 15 step 2.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError

from apps.core.exceptions import Invalid
from apps.core.services import set_exchange_rate


class Command(BaseCommand):
    help = "Record a monthly exchange rate, closing the previous row for the pair."

    def add_arguments(self, parser):
        parser.add_argument("from_currency")
        parser.add_argument("to_currency")
        parser.add_argument("rate")
        parser.add_argument("--effective-from", required=True, help="YYYY-MM-01")
        parser.add_argument(
            "--replace",
            action="store_true",
            help="replace the rate already recorded for that month",
        )

    def handle(self, *args, **options):
        try:
            rate = Decimal(options["rate"])
            effective_from = date.fromisoformat(options["effective_from"])
        except (InvalidOperation, ValueError) as exc:
            raise CommandError(f"bad argument: {exc}") from exc
        try:
            row = set_exchange_rate(
                options["from_currency"],
                options["to_currency"],
                rate,
                effective_from,
                replace=options["replace"],
            )
        except Invalid as exc:
            raise CommandError(
                "; ".join(f"{k}: {', '.join(v)}" for k, v in exc.errors.items())
            ) from exc
        self.stdout.write(
            f"1 {row.from_currency} = {row.rate} {row.to_currency} from {row.effective_from}"
        )
