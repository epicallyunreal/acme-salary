"""A staged row carries the sheet's legacy_code, the column that replaces EmployeeID (D48)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("imports", "0001_initial"),
    ]

    operations = [
        migrations.RenameField(
            model_name="importrow", old_name="employee_code", new_name="legacy_code"
        ),
        migrations.AlterField(
            model_name="importrow",
            name="legacy_code",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
    ]
