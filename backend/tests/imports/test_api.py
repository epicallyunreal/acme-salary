"""The import endpoints over HTTP (SPEC F1, F2, section 8): shapes, filters, refusals and the
pinned query counts. Staging itself is tested in test_staging."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook

from apps.audit import services as audit_services
from apps.audit.models import AuditLog
from apps.imports.models import ImportBatch
from apps.imports.services import stage_upload
from tests.imports.sheets import HEADER, RAISED, new_row, sheet_row, upload_of

pytestmark = pytest.mark.django_db

LIST = "/api/v1/imports/"
BATCH_KEYS = {
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
}


def post_file(api, upload):
    return api.post(LIST, {"file": upload}, format="multipart")


def numbers(response) -> list[int]:
    assert response.status_code == 200, response.content
    return [row["row_number"] for row in response.json()["results"]]


def test_an_upload_is_staged_for_review_and_answers_with_the_batch(api, staff):
    response = post_file(api, upload_of(new_row(), sheet_row(staff["asha"])))

    body = response.json()
    assert response.status_code == 201, response.content
    assert set(body) == BATCH_KEYS
    assert (body["status"], body["file_name"], body["uploaded_by"]) == (
        "review",
        "october.csv",
        "hr@acme.example",
    )
    assert (body["total_rows"], body["valid_rows"], body["noop_rows"]) == (2, 2, 1)
    assert body["uploaded_at"] == "2026-10-07T09:00:00+00:00"


def test_an_unmappable_header_is_a_400_and_no_batch_exists(api, lookups):
    """SPEC F1 acceptance: a file missing country_code names it, and nothing is staged."""
    header = [column for column in HEADER if column != "country_code"]

    response = post_file(api, upload_of(new_row(), header=header))

    assert (response.status_code, response.json()) == (
        400,
        {"missing_columns": ["Missing required column: country_code"], "unknown_columns": []},
    )
    assert ImportBatch.objects.count() == 0


@pytest.mark.parametrize(
    ("upload", "errors"),
    [
        (
            SimpleUploadedFile("notes.txt", b"legacy_code\n", content_type="text/plain"),
            {"file": ["file must end in .xlsx or .csv, got notes.txt"]},
        ),
        (
            SimpleUploadedFile("a.csv", "full_name\nAndrés".encode("latin-1"), "text/csv"),
            {"file": ["file is not UTF-8"]},
        ),
        (None, {"file": ["No file was submitted."]}),
    ],
)
def test_a_file_that_cannot_be_read_is_a_400(api, lookups, upload, errors):
    response = api.post(LIST, {} if upload is None else {"file": upload}, format="multipart")

    assert (response.status_code, response.json()) == (400, errors)
    assert ImportBatch.objects.count() == 0


def test_an_upload_over_ten_megabytes_is_a_413_before_it_is_read(api, lookups):
    big = SimpleUploadedFile("big.csv", b"x" * (10 * 1024 * 1024 + 70 * 1024), "text/csv")

    response = post_file(api, big)

    assert (response.status_code, response.json()) == (
        413,
        {"detail": "upload is larger than the 10 MB limit"},
    )
    assert ImportBatch.objects.count() == 0


def test_an_xlsx_upload_is_staged_like_a_csv(api, staff):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADER)
    row = new_row()
    sheet.append([row.get(column) for column in HEADER])
    stream = io.BytesIO()
    workbook.save(stream)
    xlsx_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    response = post_file(api, SimpleUploadedFile("joiners.xlsx", stream.getvalue(), xlsx_type))

    assert response.status_code == 201, response.content
    assert (response.json()["total_rows"], response.json()["valid_rows"]) == (1, 1)


def test_the_batch_list_is_newest_first_and_the_detail_is_one_batch(api, lookups):
    first = stage_upload(upload_of(new_row()), actor=None)
    second = stage_upload(upload_of(new_row(legacy_code="HR-20002")), actor=None)

    listed = api.get(LIST).json()
    detail = api.get(f"{LIST}{first.pk}/")

    assert listed["count"] == 2
    assert [batch["id"] for batch in listed["results"]] == [second.pk, first.pk]
    assert (detail.status_code, detail.json()["id"], detail.json()["uploaded_by"]) == (
        200,
        first.pk,
        None,
    )
    assert api.get(f"{LIST}999999/").status_code == 404


def test_rows_filter_by_status_and_search_by_code_or_name(api, staff):
    batch = stage_upload(
        upload_of(
            new_row(),
            sheet_row(staff["asha"]),
            new_row(
                legacy_code="HR-20002",
                email="ravi@acme.example",
                full_name="Ravi Menon",
                BASE=-5000,
            ),
        ),
        actor=None,
    )
    url = f"{LIST}{batch.pk}/rows/"

    rows = api.get(url).json()["results"]

    assert [row["row_number"] for row in rows] == [2, 3, 4]
    assert set(rows[1]) == {
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
        "normalized",
    }
    asha = staff["asha"]
    assert rows[1]["matched_employee"] == {"id": asha.pk, "employee_code": asha.employee_code}
    assert rows[0]["matched_employee"] is None
    assert (rows[2]["raw"]["BASE"], rows[2]["normalized"]["amounts"]["BASE"]) == ("-5000", "-5000")
    assert numbers(api.get(url, {"status": "error"})) == [4]
    assert numbers(api.get(url, {"status": "error,valid"})) == [2, 3, 4]
    assert numbers(api.get(url, {"search": "HR-10001"})) == [3]
    assert numbers(api.get(url, {"search": "ravi"})) == [4]
    assert numbers(api.get(url, {"page_size": 2, "page": 2})) == [4]
    bad = api.get(url, {"status": "gone"})
    assert (bad.status_code, bad.json()) == (
        400,
        {"status": ["Select a valid choice. gone is not one of the available choices."]},
    )


def test_the_rows_of_an_unknown_batch_are_a_404(api, lookups):
    assert api.get(f"{LIST}999999/rows/").status_code == 404


def test_list_detail_and_rows_query_counts(api, staff, django_assert_num_queries):
    """User from the JWT, then the count and the page with the uploader for the list, the
    batch for the detail, and the batch, the count and the page for the rows."""
    batch = stage_upload(upload_of(new_row(), sheet_row(staff["asha"])), actor=None)

    with django_assert_num_queries(3):
        api.get(LIST)
    with django_assert_num_queries(2):
        api.get(f"{LIST}{batch.pk}/")
    with django_assert_num_queries(4):
        api.get(f"{LIST}{batch.pk}/rows/")


def test_skip_and_unskip_answer_with_the_row_and_move_the_counts(api, staff):
    batch = stage_upload(upload_of(sheet_row(staff["gita"], **RAISED), new_row()), actor=None)
    row = batch.rows.get(row_number=2)
    url = f"{LIST}{batch.pk}/rows/{row.pk}/"

    skipped = api.post(f"{url}skip/")
    counts = api.get(f"{LIST}{batch.pk}/").json()
    unskipped = api.post(f"{url}unskip/")

    assert (skipped.status_code, skipped.json()["status"]) == (200, "skipped")
    assert skipped.json()["validation_status"] == "error"
    assert (counts["skipped_rows"], counts["error_rows"]) == (1, 0)
    assert (unskipped.status_code, unskipped.json()["status"]) == (200, "error")


def test_a_row_of_another_batch_or_an_unknown_id_is_a_404(api, lookups):
    first = stage_upload(upload_of(new_row()), actor=None)
    second = stage_upload(upload_of(new_row(legacy_code="HR-20002")), actor=None)
    elsewhere = second.rows.get()

    assert api.post(f"{LIST}{first.pk}/rows/{elsewhere.pk}/skip/").status_code == 404
    assert api.post(f"{LIST}{first.pk}/rows/999999/unskip/").status_code == 404
    assert api.post(f"{LIST}999999/approve/").status_code == 404
    assert api.post(f"{LIST}999999/discard/").status_code == 404


def test_approve_names_the_error_count_then_applies_once(api, staff, hr_user):
    batch = stage_upload(upload_of(sheet_row(staff["gita"], **RAISED), new_row()), actor=None)

    refused = api.post(f"{LIST}{batch.pk}/approve/")
    api.post(f"{LIST}{batch.pk}/rows/{batch.rows.get(row_number=2).pk}/skip/")
    approved = api.post(f"{LIST}{batch.pk}/approve/")
    again = api.post(f"{LIST}{batch.pk}/approve/")

    assert (refused.status_code, refused.json()) == (
        409,
        {"detail": "1 row has errors", "error_rows": 1},
    )
    assert approved.status_code == 200, approved.content
    assert (approved.json()["status"], approved.json()["applied_rows"]) == ("approved", 1)
    assert (again.status_code, again.json()) == (
        409,
        {"detail": "the batch is approved, not in review"},
    )
    assert AuditLog.objects.get(action="import_apply").actor == hr_user


def test_a_failed_approve_is_a_409_with_the_summary(api, lookups, monkeypatch):
    batch = stage_upload(upload_of(new_row()), actor=None)

    def disk_full(entries):
        raise OSError("disk full")

    monkeypatch.setattr(audit_services, "bulk_record", disk_full)

    response = api.post(f"{LIST}{batch.pk}/approve/")

    assert (response.status_code, response.json()) == (
        409,
        {
            "detail": "approve failed, the batch is marked failed",
            "error_summary": "OSError: disk full",
        },
    )
    assert api.get(f"{LIST}{batch.pk}/").json()["status"] == "failed"


def test_discard_sets_a_batch_aside_once(api, lookups):
    batch = stage_upload(upload_of(new_row()), actor=None)

    response = api.post(f"{LIST}{batch.pk}/discard/")

    assert (response.status_code, response.json()["status"]) == (200, "discarded")
    assert api.post(f"{LIST}{batch.pk}/discard/").json() == {
        "detail": "the batch is discarded, not in review"
    }
