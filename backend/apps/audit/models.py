"""One row per write to employee or compensation data, with before and after snapshots.

SPEC section 5, AuditLog.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.employees.models import Employee
from apps.imports.models import ImportBatch


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        EXIT = "exit", "Exit"
        REVISE = "revise", "Revise"
        CANCEL = "cancel", "Cancel"
        IMPORT_APPLY = "import_apply", "Import apply"
        SET_RATE = "set_rate", "Set rate"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    action = models.CharField(max_length=16, choices=Action.choices)
    entity_type = models.CharField(max_length=32)
    entity_id = models.BigIntegerField()
    employee = models.ForeignKey(
        Employee, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_entries"
    )
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    import_batch = models.ForeignKey(
        ImportBatch, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_entries"
    )

    class Meta:
        ordering = ["-timestamp", "-id"]
        indexes = [models.Index(fields=["entity_type", "entity_id"], name="audit_entity")]

    def __str__(self) -> str:
        return f"{self.action} {self.entity_type}:{self.entity_id}"
