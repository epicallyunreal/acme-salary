"""Every validation message pattern of SPEC section 7, in one place.

The parser (step 5) and the rules in validators.py both format their text here, so a message is
worded the same wherever it is raised.
"""

MESSAGES = {
    "missing_column": "Missing required column: {column}",
    "unknown_column": "Ignored unknown column: {column}",
    "not_utf8": "file is not UTF-8",
    "file_extension": "file must end in .xlsx or .csv, got {name}",
    "file_content_type": "file content type {content_type} does not match {extension}",
    "file_unreadable": (
        "file is not a readable .xlsx workbook; save it again from Excel and upload it"
    ),
    "csv_unreadable": "file is not a readable .csv; save it again from Excel and upload it",
    "file_unpacks_large": "file unpacks to more than {limit}",
    "file_too_big": "file is too big to read",
    "upload_busy": "another file is being read; try again in a moment",
    "row_too_wide": "row {row} has more than {limit} cells",
    "row_past_limit": "row {row} is past row {limit}",
    "cell_required": "{field} is required",
    "file_no_header": "file has no header row",
    "row_limit": "file has {count} data rows, limit {limit}",
    "column_twice": "{column} appears twice in the header; remove one",
    "legacy_ambiguous": (
        "{columns} could {quantity} be the legacy code; rename the right one to legacy_code"
    ),
    "legacy_required": "legacy_code is required",
    "legacy_too_long": "legacy_code is longer than {limit} characters",
    "text_too_long": "{field} is longer than {limit} characters",
    "legacy_duplicate": "Duplicate legacy_code in rows {first} and {second}",
    "action_changed": "{employee} changed since this sheet was uploaded; upload the sheet again",
    "legacy_taken": "legacy_code {code} now belongs to {employee}; upload the sheet again",
    "code_assigned": "employee_code is assigned by the system",
    "legacy_import_only": "legacy_code is set only by an import",
    "line_twice": "{code} appears twice in lines",
    "email_invalid": "email is not a valid address",
    "email_duplicate": "Duplicate email in rows {first} and {second}",
    "email_in_use": "email already belongs to {code}",
    "country_unknown": "Unknown country_code: {value}",
    "country_changed": "country change is not supported by import",
    "country_fixed": "country_code cannot be changed",
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
    "base_too_small": "BASE must be at least {minimum}, got {value}",
    "amount_too_large": "{field} must be at most {limit}, got {value}",
    "date_too_late": "{field} must be on or before {limit}, got {value}",
    "bonus_above_base": "bonus_annual {bonus} is above BASE {base}",
    "deduction_above_base": "{code} {amount} is above BASE {base}",
    "bonus_invalid": "bonus_annual must be a non-negative number, got {value}",
    "deductions_exceed_gross": "deductions exceed gross",
    "gross_below_minimum": "gross {gross} {currency} is below the {country} minimum {minimum}",
    "gross_above_median": (
        "gross {gross} {currency} is above ten times the {country} median {median}"
    ),
    "noop": "No changes, row will be skipped on apply",
    "effective_defaulted": "effective_from defaulted to joining_date {date}",
}


# A message repeats at most this much of any value it names (D56): a sheet cell can be
# 100,000 characters, and messages are stored on every staged row.
ECHO_LIMIT = 64


def clip(value: object, limit: int = ECHO_LIMIT) -> str:
    """`value` as text, cut to `limit` characters with an ellipsis when it is longer."""
    text = str(value)
    return text if len(text) <= limit else f"{text[: limit - 1]}\u2026"


def msg(key: str, **values) -> str:
    return MESSAGES[key].format(**{name: clip(value) for name, value in values.items()})
