"""Output shapes for the directory and the employee detail (SPEC section 8, DESIGN 1.3).

Serializers read; they never compute totals. Converted amounts come from the RateTable in the
context through core/fx.py, so no conversion lives here.
"""

from rest_framework import serializers

from apps.compensation.models import CompensationLine, CompensationRecord
from apps.core.money import q8, render
from apps.employees.models import Employee
from apps.employees.queries import is_current, pick_shown, shown_label, status_on


class LineSerializer(serializers.ModelSerializer):
    component = serializers.SerializerMethodField()

    class Meta:
        model = CompensationLine
        fields = ("component", "annual_amount")

    def get_component(self, line):
        return {
            "code": line.component.code,
            "name": line.component.name,
            "kind": line.component.kind,
        }


class CompensationRecordSerializer(serializers.ModelSerializer):
    lines = LineSerializer(many=True, read_only=True)
    is_current = serializers.SerializerMethodField()
    is_scheduled = serializers.SerializerMethodField()
    cancelled_by = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    converted = serializers.SerializerMethodField()

    class Meta:
        model = CompensationRecord
        fields = (
            "id",
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


class DepartmentField(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()


class CountryField(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    currency_code = serializers.CharField()


class EmployeeListSerializer(serializers.ModelSerializer):
    """One directory row. `shown` is the record current on the reporting date, else the latest."""

    department = DepartmentField(read_only=True)
    country = CountryField(read_only=True)
    status = serializers.CharField(read_only=True)
    shown = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = (
            "id",
            "employee_code",
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
    department = DepartmentField(read_only=True)
    country = CountryField(read_only=True)
    status = serializers.SerializerMethodField()
    shown_label = serializers.SerializerMethodField()
    current_record = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = (
            "id",
            "employee_code",
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
