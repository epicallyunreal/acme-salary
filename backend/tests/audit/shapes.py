"""What an audit snapshot holds of an API response: everything but the request-dependent keys.

Shared by the snapshot tests and the audit API tests, so a new request-dependent serializer key
is added once (D34).
"""

RECORD_REQUEST_KEYS = {"converted", "is_current", "is_scheduled"}
EMPLOYEE_REQUEST_KEYS = {"status", "shown_label"}


def record_shape(data: dict) -> dict:
    return {key: value for key, value in data.items() if key not in RECORD_REQUEST_KEYS}


def employee_shape(data: dict) -> dict:
    shape = {key: value for key, value in data.items() if key not in EMPLOYEE_REQUEST_KEYS}
    if shape["current_record"] is not None:
        shape["current_record"] = record_shape(shape["current_record"])
    return shape
