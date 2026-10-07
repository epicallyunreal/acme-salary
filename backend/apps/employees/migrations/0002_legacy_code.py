"""The employee code becomes ACME-<id>, and the stored code moves to legacy_code (D48).

Today's employee_code values are copied into legacy_code before the column is dropped, so a
database seeded before this change can still find every employee until reset_demo rebuilds it.
"""

from django.db import migrations, models


def copy_codes_to_legacy(apps, schema_editor):
    Employee = apps.get_model("employees", "Employee")
    Employee.objects.update(legacy_code=models.F("employee_code"))


class Migration(migrations.Migration):
    dependencies = [
        ("employees", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="legacy_code",
            field=models.CharField(blank=True, max_length=32, null=True, unique=True),
        ),
        migrations.RunPython(copy_codes_to_legacy, migrations.RunPython.noop),
        migrations.RemoveField(model_name="employee", name="employee_code"),
        migrations.AddConstraint(
            model_name="employee",
            constraint=models.CheckConstraint(
                condition=models.Q(("legacy_code__isnull", True)) | ~models.Q(("legacy_code", "")),
                name="employee_legacy_code_not_empty",
            ),
        ),
    ]
