"""Lookups and the exchange-rate table (SPEC section 5, "Lookups")."""

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Country(models.Model):
    code = models.CharField(max_length=2, primary_key=True)
    name = models.CharField(max_length=80)
    currency_code = models.CharField(max_length=3)
    min_gross_annual = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "countries"

    def __str__(self) -> str:
        return self.code


class Department(models.Model):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=80)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.code


class ExchangeRate(models.Model):
    """1 from_currency = rate to_currency, for the month starting at effective_from."""

    from_currency = models.CharField(max_length=3)
    to_currency = models.CharField(max_length=3)
    rate = models.DecimalField(max_digits=18, decimal_places=8)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["from_currency", "to_currency", "effective_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["from_currency", "to_currency", "effective_from"],
                name="exchange_rate_one_per_pair_and_month",
            ),
            models.UniqueConstraint(
                fields=["from_currency", "to_currency"],
                condition=Q(effective_to__isnull=True),
                name="exchange_rate_one_open_per_pair",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True) | Q(effective_to__gt=F("effective_from")),
                name="exchange_rate_half_open",
            ),
            models.CheckConstraint(condition=Q(rate__gt=0), name="exchange_rate_positive"),
            models.CheckConstraint(
                condition=~Q(from_currency=F("to_currency")), name="exchange_rate_distinct_pair"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.from_currency}->{self.to_currency} {self.rate} from {self.effective_from}"


class SalaryComponent(models.Model):
    class Kind(models.TextChoices):
        EARNING = "earning", "Earning"
        DEDUCTION = "deduction", "Deduction"
        EMPLOYER_CONTRIBUTION = "employer_contribution", "Employer contribution"

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=24, choices=Kind.choices)
    country = models.ForeignKey(
        Country, null=True, blank=True, on_delete=models.PROTECT, related_name="components"
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "code"]

    def __str__(self) -> str:
        return self.code
