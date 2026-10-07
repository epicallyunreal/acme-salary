"""Input shape of a compensation record (SPEC section 8, DESIGN 1.3).

Shape and types only. The rules live in validators.py and run inside the services, so the API
answers with SPEC section 7's messages. A component listed twice in `lines` is refused here,
because turning the list into a per-component mapping would otherwise keep the last one (D44).
"""

from rest_framework import serializers

from apps.compensation.services import ZERO, RecordInput


class LineInputSerializer(serializers.Serializer):
    component = serializers.CharField()
    annual_amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class RecordInputSerializer(serializers.Serializer):
    """`POST /employees/{id}/compensation/`: `{effective_from, bonus_annual, note, lines}`.

    `effective_from` may be left out so the validators answer `effective_from is required when
    amounts change`, the same message an import row gets. A missing bonus is zero (SPEC F1).
    """

    effective_from = serializers.DateField(allow_null=True, default=None)
    bonus_annual = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    note = serializers.CharField(allow_blank=True, default="")
    lines = LineInputSerializer(many=True)

    def validate_lines(self, lines):
        seen: set[str] = set()
        for line in lines:
            code = line["component"]
            if code in seen:
                raise serializers.ValidationError(f"{code} appears twice in lines")
            seen.add(code)
        return lines

    def record_input(self) -> RecordInput:
        data = self.validated_data
        return RecordInput(
            effective_from=data["effective_from"],
            bonus_annual=data.get("bonus_annual", ZERO),
            note=data["note"],
            lines={line["component"]: line["annual_amount"] for line in data["lines"]},
        )
