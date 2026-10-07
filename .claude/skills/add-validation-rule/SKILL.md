---
name: add-validation-rule
description: Recipe for adding or changing an import or form validation rule. Use when a new check on employee or compensation data is needed, or when the user says "validate X", "reject rows where", or "flag Y as a warning".
---

# Add a validation rule

All rules live in `backend/apps/compensation/validators.py` and are called by the services for the import pipeline, the API and the seed. Serializers check shape and types only and never call them. Never add a business check anywhere else.

1. Check `docs/SPEC.md` section 7. The rule must be in the table with its severity and message pattern. If it is a new rule, stop and ask the human to add it to the spec first.
2. Write the rule as a small function `check_<name>(row: NormalizedRow, ctx: ValidationContext) -> list[Message]`, where `Message` is `{field, severity, message}` and severity is `error`, `warning` or `info`. The context carries lookups the rule needs (country codes, department codes, component codes per country, the employee's current record) so the rule itself does no database access.
3. Register it in the ordered `RULES` list. The order is SPEC F1's: structure and types, identity references, duplicate code and email within the file, amounts changed, no-op, then date rules. The no-op check runs before the date check so an unchanged row is never a date error.
4. Message text follows the spec pattern exactly, with the real field and value substituted, for example `BASE must be a non-negative number, got -5000`.
5. Tests in `tests/compensation/test_validators.py`: one passing case and one failing case per rule, asserting field, severity and the full message. For `effective_from` and duplicate checks, build the context with a factory-made current record.
6. Confirm the import pipeline picks it up: a test in `tests/imports/` that uploads a two-row file where one row trips the new rule and asserts the row status and message.
7. If the rule changes which rows the review grid shows as errors, update the MSW fixture in `frontend/src/test/` and the review grid test.
