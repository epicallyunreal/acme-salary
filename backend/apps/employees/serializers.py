"""Shapes for the directory, the employee detail, the history, the audit list and the employee
writes (SPEC section 8, DESIGN 1.3).

Output serializers read; they never compute totals. Converted amounts come from the RateTable in
the context through core/fx.py. The record and employee shapes are what audit.snapshot_record and
audit.snapshot_employee write, plus the request-dependent keys, and tests/audit/test_snapshots.py
holds them equal (D34). Input serializers check shape and types only: the rules run in the
services, so the API answers with SPEC section 7's messages.
"""

from rest_framework import serializers

from apps.audit.models import AuditLog
from apps.compensation.models import CompensationLine, CompensationRecord
from apps.compensation.serializers import LOOKUP_MAX, RecordInputSerializer
from apps.core.money import q8, render
from apps.employees.models import Employee
from apps.employees.queries import is_current, pick_shown, shown_label, status_on

# What a create passes to the service. The two codes are read so the service can refuse them
# with a 400 instead of the serializer dropping them silently (D48).
CREATE_IDENTITY_FIELDS = (
    "employee_code",
    "legacy_code",
    "full_name",
    "email",
    "department",
    "designation",
    "level",
    "country_code",
    "gender",
    "joining_date",
)


class SnapshotDateTimeField(serializers.DateTimeField):
    """ISO text as the audit snapshots write it (`+00:00`, where DRF would write `Z`), so an
    audit entry's before and after equal what this API shows (D34)."""

    def to_representation(self, value):
        return render(value)


class LineSerializer(serializers.ModelSerializer):
    """A line as the audit snapshot writes it: the component's code. The client reads names and
    kinds from /meta/components/ (D34)."""

    component = serializers.SlugRelatedField(slug_field="code", read_only=True)

    class Meta:
        model = CompensationLine
        fields = ("component", "annual_amount")


class CompensationRecordSerializer(serializers.ModelSerializer):
    lines = LineSerializer(many=True, read_only=True)
    is_current = serializers.SerializerMethodField()
    is_scheduled = serializers.SerializerMethodField()
    cancelled_at = SnapshotDateTimeField(read_only=True)
    cancelled_by = serializers.SerializerMethodField()
    created_at = SnapshotDateTimeField(read_only=True)
    created_by = serializers.SerializerMethodField()
    converted = serializers.SerializerMethodField()

    class Meta:
        model = CompensationRecord
        fields = (
            "id",
            "employee",
            "version",
            "effective_from",
            "effective_to",
            "is_current",
            "is_scheduled",
            "cancelled_at",
            "cancelled_by",
            "currency_code",
            "bonus_annual",
            "gross_annual",
            "net_annual",
            "total_cost_annual",
            "source",
            "note",
            "created_at",
            "created_by",
            "lines",
            "converted",
        )
        read_only_fields = fields

    def get_is_current(self, record):
        return is_current(record, self.context["on"])

    def get_is_scheduled(self, record):
        return record.cancelled_at is None and record.effective_from > self.context["on"]

    def get_cancelled_by(self, record):
        return record.cancelled_by.email if record.cancelled_by_id else None

    def get_created_by(self, record):
        return record.created_by.email if record.created_by_id else None

    def get_converted(self, record):
        rates = self.context["rates"]
        currency = self.context["reporting_currency"]

        def convert(amount):
            return rates.convert(amount, record.currency_code, currency)

        return render(
            {
                "currency": currency,
                "rate": q8(rates.rate(record.currency_code, currency)),
                "rate_effective_from": rates.effective_from(record.currency_code, currency),
                "bonus_annual": convert(record.bonus_annual),
                "gross_annual": convert(record.gross_annual),
                "net_annual": convert(record.net_annual),
                "total_cost_annual": convert(record.total_cost_annual),
            }
        )


class DepartmentSummarySerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class CountrySummarySerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    currency_code = serializers.CharField()


class EmployeeListSerializer(serializers.ModelSerializer):
    """One directory row. `shown` is the record current on the reporting date, else the latest."""

    department = DepartmentSummarySerializer(read_only=True)
    country = CountrySummarySerializer(read_only=True)
    status = serializers.CharField(read_only=True)
    shown = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = (
            "id",
            "employee_code",
            "legacy_code",
            "full_name",
            "email",
            "department",
            "designation",
            "level",
            "country",
            "status",
            "joining_date",
            "last_date",
            "shown",
        )
        read_only_fields = fields

    def get_shown(self, employee):
        on = self.context["on"]
        rates = self.context["rates"]
        currency = self.context["reporting_currency"]
        record = pick_shown(employee.live_records, on)
        if record is None:
            return None
        return render(
            {
                "record_id": record.pk,
                "version": record.version,
                "effective_from": record.effective_from,
                "effective_to": record.effective_to,
                "is_current": is_current(record, on),
                "label": shown_label(employee, record, on),
                "gross_local": record.gross_annual,
                "currency_code": record.currency_code,
                "gross_reporting": rates.convert(
                    record.gross_annual, record.currency_code, currency
                ),
                "reporting_currency": currency,
            }
        )


class EmployeeDetailSerializer(serializers.ModelSerializer):
    department = DepartmentSummarySerializer(read_only=True)
    country = CountrySummarySerializer(read_only=True)
    status = serializers.SerializerMethodField()
    shown_label = serializers.SerializerMethodField()
    current_record = serializers.SerializerMethodField()
    created_at = SnapshotDateTimeField(read_only=True)
    updated_at = SnapshotDateTimeField(read_only=True)

    class Meta:
        model = Employee
        fields = (
            "id",
            "employee_code",
            "legacy_code",
            "full_name",
            "email",
            "gender",
            "department",
            "designation",
            "level",
            "country",
            "joining_date",
            "last_date",
            "status",
            "shown_label",
            "current_record",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def _shown(self, employee):
        return pick_shown(employee.live_records, self.context["on"])

    def get_status(self, employee):
        return status_on(employee, self.context["on"])

    def get_shown_label(self, employee):
        return shown_label(employee, self._shown(employee), self.context["on"])

    def get_current_record(self, employee):
        record = self._shown(employee)
        if record is None:
            return None
        return CompensationRecordSerializer(record, context=self.context).data


class AuditEntrySerializer(serializers.ModelSerializer):
    """One audit row as the employee page lists it: who, when, what changed (SPEC F7)."""

    timestamp = SnapshotDateTimeField(read_only=True)
    actor = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "timestamp",
            "actor",
            "action",
            "entity_type",
            "entity_id",
            "before",
            "after",
            "import_batch",
        )
        read_only_fields = fields

    def get_actor(self, entry):
        return entry.actor.email if entry.actor_id else None


# Input


class EmployeeCreateSerializer(RecordInputSerializer):
    """`POST /employees/`: identity, bonus and the first record's lines in one body. The database
    numbers the employee; either code in the body is refused by the service (D48)."""

    employee_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    legacy_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    full_name = serializers.CharField(max_length=120)
    email = serializers.CharField(max_length=254)
    department = serializers.CharField(max_length=LOOKUP_MAX)
    designation = serializers.CharField(max_length=80)
    level = serializers.IntegerField()
    country_code = serializers.CharField(max_length=LOOKUP_MAX)
    gender = serializers.CharField(max_length=LOOKUP_MAX)
    joining_date = serializers.DateField()

    def identity(self) -> dict:
        return {
            name: self.validated_data[name]
            for name in CREATE_IDENTITY_FIELDS
            if name in self.validated_data
        }


class EmployeeIdentitySerializer(serializers.Serializer):
    """`PATCH /employees/{id}/`: any identity field. The two codes and `country_code` are read so
    the service refuses them with a 400 instead of the serializer dropping them (D48)."""

    employee_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    legacy_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    country_code = serializers.CharField(max_length=LOOKUP_MAX, required=False)
    full_name = serializers.CharField(max_length=120, required=False)
    email = serializers.CharField(max_length=254, required=False)
    department = serializers.CharField(max_length=LOOKUP_MAX, required=False)
    designation = serializers.CharField(max_length=80, required=False)
    level = serializers.IntegerField(required=False)
    gender = serializers.CharField(max_length=LOOKUP_MAX, required=False)
    joining_date = serializers.DateField(required=False)


class ExitSerializer(serializers.Serializer):
    last_date = serializers.DateField()
