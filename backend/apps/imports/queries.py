"""Read side of the import pipeline (DESIGN 1.5)."""

from django.db.models import QuerySet

from apps.imports.models import ImportBatch, ImportRow


def batch_queryset() -> QuerySet[ImportBatch]:
    """Batches newest first, with the uploader for the list."""
    return ImportBatch.objects.select_related("uploaded_by").order_by("-uploaded_at", "-id")


def rows_queryset(batch_id: int) -> QuerySet[ImportRow]:
    """One batch's rows in sheet order."""
    return ImportRow.objects.filter(batch_id=batch_id).order_by("row_number")
