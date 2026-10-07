"""Staging tables for spreadsheet imports (SPEC section 5). Live tables wait for approval."""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.employees.models import Employee


class ImportBatch(models.Model):
    class Status(models.TextChoices):
        REVIEW = "review", "Review"
        APPROVED = "approved", "Approved"
        DISCARDED = "discarded", "Discarded"
        FAILED = "failed", "Failed"

    file_name = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    uploaded_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REVIEW)
    warnings = models.JSONField(default=list, blank=True)
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    warning_rows = models.PositiveIntegerField(default=0)
    error_rows = models.PositiveIntegerField(default=0)
    skipped_rows = models.PositiveIntegerField(default=0)
    noop_rows = models.PositiveIntegerField(default=0)
    created_rows = models.PositiveIntegerField(default=0)
    updated_rows = models.PositiveIntegerField(default=0)
    revised_rows = models.PositiveIntegerField(default=0)
    applied_rows = models.PositiveIntegerField(default=0)
    approved_at = models.DateTimeField(null=True, blank=True)
    error_summary = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-uploaded_at", "-id"]
        verbose_name_plural = "import batches"

    def __str__(self) -> str:
        return f"{self.file_name} ({self.status})"


class ImportRow(models.Model):
    class Status(models.TextChoices):
        VALID = "valid", "Valid"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"
        SKIPPED = "skipped", "Skipped"

    class ValidationStatus(models.TextChoices):
        VALID = "valid", "Valid"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        REVISE = "revise", "Revise"
        NOOP = "noop", "No-op"

    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField()
    employee_code = models.CharField(max_length=16, blank=True, default="")
    full_name = models.CharField(max_length=120, blank=True, default="")
    raw = models.JSONField(default=dict, blank=True)
    normalized = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices)
    validation_status = models.CharField(max_length=8, choices=ValidationStatus.choices)
    messages = models.JSONField(default=list, blank=True)
    # SPEC section 5: null when the row has no usable EmployeeID, so null is the contract here.
    action = models.CharField(max_length=8, choices=Action.choices, null=True, blank=True)  # noqa: DJ001
    matched_employee = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["batch_id", "row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "row_number"], name="import_row_number_per_batch"
            )
        ]
        indexes = [models.Index(fields=["batch", "status"], name="import_row_batch_status")]

    def __str__(self) -> str:
        return f"row {self.row_number} ({self.status})"
