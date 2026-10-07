"""Effective-dated compensation records with one line per component (SPEC section 5).

Models hold fields, constraints and indexes only. Every rule lives in services.py.
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import SalaryComponent
from apps.employees.models import Employee


class Source(models.TextChoices):
    UI = "ui", "UI"
    IMPORT = "import", "Import"
    SEED = "seed", "Seed"


class CompensationRecord(models.Model):
    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT, related_name="compensation_records"
    )
    version = models.PositiveSmallIntegerField()
    currency_code = models.CharField(max_length=3)
    bonus_annual = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    gross_annual = models.DecimalField(max_digits=14, decimal_places=2, db_index=True)
    net_annual = models.DecimalField(max_digits=14, decimal_places=2)
    total_cost_annual = models.DecimalField(max_digits=14, decimal_places=2)
    source = models.CharField(max_length=8, choices=Source.choices)
    import_batch = models.ForeignKey(
        "imports.ImportBatch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="records",
    )
    note = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["employee_id", "effective_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "version"], name="compensation_record_version_per_employee"
            ),
            # Live rows only: a cancelled revision releases its date, so cancel and re-enter on
            # the same day works (D43). Versions stay unique across every row.
            models.UniqueConstraint(
                fields=["employee", "effective_from"],
                condition=Q(cancelled_at__isnull=True),
                name="compensation_record_live_effective_from",
            ),
            models.UniqueConstraint(
                fields=["employee"],
                condition=Q(effective_to__isnull=True, cancelled_at__isnull=True),
                name="one_open_live_record",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True) | Q(effective_to__gt=F("effective_from")),
                name="compensation_record_half_open",
            ),
            models.CheckConstraint(
                condition=Q(bonus_annual__gte=0), name="compensation_record_bonus_non_negative"
            ),
        ]
        indexes = [
            models.Index(fields=["employee", "effective_to"], name="comp_record_employee_to"),
            models.Index(fields=["employee", "effective_from"], name="comp_record_employee_from"),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} v{self.version} from {self.effective_from}"


class CompensationLine(models.Model):
    record = models.ForeignKey(CompensationRecord, on_delete=models.CASCADE, related_name="lines")
    component = models.ForeignKey(SalaryComponent, on_delete=models.PROTECT, related_name="+")
    annual_amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["record_id", "component__sort_order", "component__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["record", "component"], name="compensation_line_component_per_record"
            ),
            models.CheckConstraint(
                condition=Q(annual_amount__gte=0), name="compensation_line_non_negative"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.component_id}={self.annual_amount}"
