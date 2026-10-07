"""Employee (SPEC section 5). Active is derived from the dates, there is no status column.

The employee code is the primary key written as ACME-<id>: the database assigns it on every
insert and nothing stores it (D48). `legacy_code` is the code an imported sheet carried, set
once when the import creates the employee, and NULL for everyone created in the app.
"""

from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import Country, Department

LEGACY_CODE_MAX = 32


def employee_code_of(pk: int | None) -> str | None:
    return f"ACME-{pk}" if pk is not None else None


class Gender(models.TextChoices):
    FEMALE = "female", "Female"
    MALE = "male", "Male"
    OTHER = "other", "Other"
    UNDISCLOSED = "undisclosed", "Undisclosed"


class Employee(models.Model):
    legacy_code = models.CharField(max_length=LEGACY_CODE_MAX, null=True, blank=True, unique=True)
    full_name = models.CharField(max_length=120, db_index=True)
    email = models.EmailField(unique=True)
    gender = models.CharField(max_length=12, choices=Gender.choices)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="employees")
    designation = models.CharField(max_length=80, db_index=True)
    level = models.PositiveSmallIntegerField(db_index=True)
    country = models.ForeignKey(Country, on_delete=models.PROTECT, related_name="employees")
    joining_date = models.DateField(db_index=True)
    last_date = models.DateField(null=True, blank=True, db_index=True)
    updated_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["full_name", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(level__gte=1) & Q(level__lte=6), name="employee_level_1_to_6"
            ),
            models.CheckConstraint(
                condition=Q(last_date__isnull=True) | Q(last_date__gte=F("joining_date")),
                name="employee_last_date_after_joining",
            ),
            models.CheckConstraint(
                condition=Q(legacy_code__isnull=True) | ~Q(legacy_code=""),
                name="employee_legacy_code_not_empty",
            ),
        ]
        indexes = [models.Index(fields=["department", "country"], name="employee_dept_country")]

    def __str__(self) -> str:
        return f"{self.employee_code} {self.full_name}"

    @property
    def employee_code(self) -> str | None:
        """ACME-<id>, no leading zeros: ACME-17 is /employees/17."""
        return employee_code_of(self.pk)
