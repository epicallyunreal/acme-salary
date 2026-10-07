"""Every validation message pattern of SPEC section 7, in one place.

The parser (step 5) and the rules in validators.py both format their text here, so a message is
worded the same wherever it is raised.
"""

MESSAGES = {
    "missing_column": "Missing required column: {column}",
    "unknown_column": "Ignored unknown column: {column}",
    "not_utf8": "file is not UTF-8",
    "code_invalid": "EmployeeID is required and must match ACME-NNNNNN",
    "code_duplicate": "Duplicate EmployeeID in rows {first} and {second}",
    "code_taken": "employee_code {code} already exists; omit employee_code to have one assigned",
    "email_invalid": "email is not a valid address",
    "email_duplicate": "Duplicate email in rows {first} and {second}",
    "email_in_use": "email already belongs to {code}",
    "country_unknown": "Unknown country_code: {value}",
    "country_changed": "country change is not supported by import",
    "department_unknown": "Unknown department: {value}",
    "level_range": "level must be between 1 and 6",
    "gender_enum": "gender must be one of female, male, other, undisclosed",
    "date_invalid": "{field} is not a valid date: {value}",
    "last_date_before_joining": "last_date precedes joining_date",
    "joining_after_first_record": "joining_date is after the first record (effective {date})",
    "last_date_before_record": "last_date precedes the current record (effective {date})",
    "last_date_cleared": "clearing last_date is not supported by import",
    "last_date_scheduled": "scheduled revision on {date} must be cancelled before exit",
    "already_exited": "employee already exited on {date}",
    "effective_before_joining": "effective_from precedes joining_date",
    "effective_not_after_latest": "effective_from must be after {date} (latest record)",
    "effective_required": "effective_from is required when amounts change",
    "revision_after_exit": "no revision after the exit on {date}",
    "component_not_applicable": "{code} is not a component for {country}",
    "amount_invalid": "{field} must be a non-negative number, got {value}",
    "comma_decimal": "use a dot as the decimal separator, got {value}",
    "too_many_decimals": "{field} has more than 2 decimal places",
    "base_required": "BASE is required",
    "bonus_invalid": "bonus_annual must be a non-negative number, got {value}",
    "deductions_exceed_gross": "deductions exceed gross",
    "gross_below_minimum": "gross {gross} {currency} is below the {country} minimum {minimum}",
    "gross_above_median": (
        "gross {gross} {currency} is above ten times the {country} median {median}"
    ),
    "noop": "No changes, row will be skipped on apply",
    "effective_defaulted": "effective_from defaulted to joining_date {date}",
}


def msg(key: str, **values) -> str:
    return MESSAGES[key].format(**values)
