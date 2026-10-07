"""Input shape of a compensation record (SPEC section 8, DESIGN 1.3).

Shape and types only. The rules live in validators.py and run inside the services, so the API
answers with SPEC section 7's messages. A component listed twice in `lines` is refused here,
because turning the list into a per-component mapping would otherwise keep the last one (D46).
Strings are capped, so no request stores or echoes an unbounded value (D51).
"""

from rest_framework import serializers

from apps.compensation.messages import msg
from apps.compensation.services import ZERO, RecordInput
from apps.compensation.validators import LOOKUP_MAX

NOTE_MAX = 1000
LINES_MAX = 20  # more than any country's components, global ones included


class LineInputSerializer(serializers.Serializer):
    component = serializers.CharField(max_length=LOOKUP_MAX)
    annual_amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class RecordInputSerializer(serializers.Serializer):
    """`POST /employees/{id}/compensation/`: `{effective_from, bonus_annual, note, lines}`.

    `effective_from` may be left out so the validators answer `effective_from is required when
    amounts change`, the same message an import row gets. A missing bonus is zero (SPEC F1).
    """

    effective_from = serializers.DateField(allow_null=True, default=None)
    bonus_annual = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    note = serializers.CharField(allow_blank=True, default="", max_length=NOTE_MAX)
    lines = LineInputSerializer(many=True, max_length=LINES_MAX)

    def validate_lines(self, lines):
        seen: set[str] = set()
        for line in lines:
            code = line["component"]
            if code in seen:
                raise serializers.ValidationError(msg("line_twice", code=code))
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
