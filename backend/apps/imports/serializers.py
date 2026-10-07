"""Shapes of batches and staged rows (SPEC section 5, DESIGN 1.5). Shape and types only."""

from rest_framework import serializers

from apps.employees.models import employee_code_of
from apps.employees.serializers import SnapshotDateTimeField
from apps.imports.models import ImportBatch, ImportRow


class ImportBatchSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.SerializerMethodField()
    uploaded_at = SnapshotDateTimeField(read_only=True)
    approved_at = SnapshotDateTimeField(read_only=True)

    class Meta:
        model = ImportBatch
        fields = [
            "id",
            "file_name",
            "file_size",
            "uploaded_by",
            "uploaded_at",
            "status",
            "warnings",
            "total_rows",
            "valid_rows",
            "warning_rows",
            "error_rows",
            "skipped_rows",
            "noop_rows",
            "created_rows",
            "updated_rows",
            "revised_rows",
            "applied_rows",
            "approved_at",
            "error_summary",
        ]
        read_only_fields = fields

    def get_uploaded_by(self, batch) -> str | None:
        return batch.uploaded_by.email if batch.uploaded_by_id else None


class ImportRowSerializer(serializers.ModelSerializer):
    """`raw` is what the sheet said, for the grid. `normalized`, what the rules read, stays on the
    server: approve reads it from the row, and the grid has no use for it."""

    matched_employee = serializers.SerializerMethodField()

    class Meta:
        model = ImportRow
        fields = [
            "id",
            "row_number",
            "legacy_code",
            "full_name",
            "status",
            "validation_status",
            "action",
            "messages",
            "matched_employee",
            "raw",
        ]
        read_only_fields = fields

    def get_matched_employee(self, row) -> dict | None:
        if row.matched_employee_id is None:
            return None
        return {
            "id": row.matched_employee_id,
            "employee_code": employee_code_of(row.matched_employee_id),
        }


class UploadSerializer(serializers.Serializer):
    file = serializers.FileField()
