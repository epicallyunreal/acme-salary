Owner decision: approved

# ACME Salary Management: Design

How the system in `docs/SPEC.md` v2.1 is built. The sections follow `.claude/skills/plan-and-design`. Model fields, API rows and validation rows are referenced by SPEC section and not restated. Where the spec leaves something open, the design names the default it assumes and lists the point under "Questions for the owner" at the end. Code is built from this document and `docs/PLAN.md` once both carry `Owner decision: approved`.

Terms used throughout:

- `on` is the reporting date, today in UTC unless passed.
- A **live record** is a `CompensationRecord` with `cancelled_at IS NULL`.
- A record is **current on `on`** when it is live and `effective_from <= on` and (`effective_to IS NULL` or `effective_to > on`).
- The **latest record** is the live record with the greatest `effective_from`, scheduled ones included. By the invariant in SPEC section 5 it is the one live record with `effective_to IS NULL`.
- The **shown record** is the record current on `on`, else the latest record. The directory, the detail page and the export use it.
- `q2(x)` is `x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`. Every amount sent to a client passes through it exactly once.

## 1. Backend module design

### 1.0 Project-level pieces

`acme_salary/settings/base.py` carries every setting; `dev.py`, `prod.py` and `test.py` override. The blocks that matter:

- `DATABASES["default"]`: sqlite3 at `DATABASE_PATH` (env, default `backend/db.sqlite3`), `OPTIONS = {"transaction_mode": "IMMEDIATE", "init_command": "PRAGMA journal_mode=WAL;", "timeout": 20}` (SPEC section 13). `test.py` uses `:memory:`.
- `REST_FRAMEWORK`: `JWTAuthentication` only, `IsAuthenticated` by default, `JSONRenderer` only (no browsable API), `DEFAULT_PAGINATION_CLASS = "apps.core.pagination.StandardPagination"`, `DEFAULT_FILTER_BACKENDS = [DjangoFilterBackend, SearchFilter]`, `DEFAULT_THROTTLE_RATES = {"login": "5/min"}`, `NUM_PROXIES = 1`, `EXCEPTION_HANDLER = "apps.core.exceptions.handler"`, `COERCE_DECIMAL_TO_STRING = True` so money leaves the API as a two-decimal string.
- `SIMPLE_JWT`: access 30 minutes, refresh 12 hours, `ROTATE_REFRESH_TOKENS = True`, `BLACKLIST_AFTER_ROTATION = True`.
- `CACHES`: `LocMemCache` (one gunicorn worker, so the throttle counter is shared by all threads).
- `INSTALLED_APPS`: `django.contrib.auth` and `contenttypes` (needed by the user model and the blacklist app), `rest_framework`, `rest_framework_simplejwt.token_blacklist`, `django_filters`, `corsheaders`, the eight apps under `apps/` and `seed`. No admin, no sessions, no messages, no staticfiles app.
- `MIDDLEWARE`: `SecurityMiddleware`, Django 6.1's `ContentSecurityPolicyMiddleware` (D38), `apps.core.middleware.NoStoreApiMiddleware` (`Cache-Control: no-store` on `/api/` responses, D41), `WhiteNoiseMiddleware`, `CorsMiddleware`, `CommonMiddleware`, `XFrameOptionsMiddleware`. JWT needs neither session nor Django's auth middleware.
- `prod.py`: `DEBUG = False`, `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` from the environment, `WHITENOISE_ROOT = SPA_DIR` (env, default `/app/spa`), `WHITENOISE_MAX_AGE = 60`, `WHITENOISE_IMMUTABLE_FILE_TEST` returning true for URLs under `/assets/`. HSTS headers are left to the `.dev` preload list.
- `acme_salary/urls.py`: `path("api/v1/", include(...))` for each app, `path("healthz", core.views.healthz)`, then `re_path(r"^(?!api/|assets/|healthz).*$", spa.index)` which returns `index.html` from `SPA_DIR` and 404 when the directory is absent (dev mode, where Vite serves the SPA).

`apps/core` holds what every app shares:

| Module | Contents |
| --- | --- |
| `pagination.py` | `StandardPagination(PageNumberPagination)`: `page_size = 25`, `page_size_query_param = "page_size"`, `max_page_size = 100` |
| `exceptions.py` | `DomainError` base. `Invalid(errors: dict[str, list[str]])` maps to `400 {field: [message]}`. `Conflict(detail, **extra)` maps to `409 {"detail": ..., ...extra}`. `PayloadTooLarge` is a DRF `APIException` with status 413. `ApplyFailed` is an `APIException` with status 409 carrying `detail` and `error_summary` (D24). `handler(exc, context)` wraps DRF's default handler and maps these four; everything else keeps DRF's shape |
| `money.py` | `q2(x)`, `to_str(x)` (two decimals), `render(payload)` walks dicts and lists turning `Decimal` into strings and dates into ISO text. Insight and exchange-rate responses pass through `render` so no `Decimal` reaches DRF's encoder, which would turn it into a float |
| `dates.py` | `today_utc()`, `parse_on(value)` (ISO date or `Invalid({"on": [...]})`), `month_label(d)` ("October 2026") |
| `filters.py` | `CharInFilter`, `NumberInFilter` (comma-separated `BaseInFilter` subclasses), `parse_csv(value) -> list[str]`, `parse_bool(value)` |
| `fx.py` | section 4 |
| `services.py` | `set_exchange_rate`, section 4 |
| `views.py` | `healthz` (a plain Django view outside DRF, runs `User.objects.order_by().exists()` so one query proves the database answers, returns `{"status": "ok"}`; the user table exists from step 1, the lookups only from step 2), the four `/meta/` views |
| `management/commands/set_exchange_rate.py`, `timing.py` | thin wrappers: parse arguments, call the service, print |

Models in `core/models.py` follow SPEC section 5 "Lookups". `ExchangeRate.Meta.constraints`: `UniqueConstraint(from_currency, to_currency, effective_from)`, `UniqueConstraint(fields=["from_currency", "to_currency"], condition=Q(effective_to__isnull=True), name="one_open_rate_per_pair")`, `CheckConstraint(condition=Q(effective_to__isnull=True) | Q(effective_to__gt=F("effective_from")))`, `CheckConstraint(condition=Q(rate__gt=0))`, `CheckConstraint(condition=~Q(from_currency=F("to_currency")))`. Django 6.1 spells these with `condition=`.

The lookup rows (six countries, twelve departments, ten components) are data, not a migration: `seed/lookups.py` has `ensure_lookups()` (idempotent `update_or_create` by code from `seed/profiles.py`) and `ensure_rates()` (the sixteen rate rows through `set_exchange_rate`, September before October). `seed_data` calls both; the test fixture `lookups` calls the first. Migrations stay schema-only, and `reset_demo` can truncate and rebuild everything the determinism scope names.

Meta endpoints (SPEC section 8): `/meta/countries/` returns `[{code, name, currency_code, min_gross_annual}]`; `/meta/departments/` returns `[{id, code, name}]`; `/meta/components/?country=` returns the global components plus that country's, ordered by `sort_order`, as `[{id, code, name, kind, country}]`, 404 for an unknown country, all components when omitted; `/meta/exchange-rates/?on=` returns `{"on", "rates": [{from_currency, to_currency, rate, effective_from}], "month_labels": {"USD": "October 2026 rates", "EUR": "October 2026 rates"}}`.

### 1.1 accounts

- Model: `User` as SPEC section 5 "Users", with a `UserManager` whose `create_user(email, password)` lowercases the email. `REQUIRED_FIELDS = []`.
- Views: `LoginView(TokenObtainPairView)` with `throttle_classes = [LoginRateThrottle]` (a `ScopedRateThrottle` that reduces an IPv6 client to its /64, D41) and `throttle_scope = "login"`; `RefreshView(TokenRefreshView)`; `LogoutView(TokenBlacklistView)` behind `IsAuthenticated`, body `{refresh}`; `MeView(APIView)` returning `{id, email}`. SimpleJWT's default serializer keys on `USERNAME_FIELD`, so the login body is `{email, password}` with no custom serializer.
- Session rules (SPEC F8, D21): `SessionRefreshSerializer(TokenRefreshSerializer)`, wired through `SIMPLE_JWT["TOKEN_REFRESH_SERIALIZER"]`, calls two functions in `accounts/services.py`. `rotate(refresh) -> (access, refresh)` blacklists the presented token and issues the pair with the original `exp` kept, so a session ends 12 hours after login, and caps the access token's `exp` at the refresh token's. `revoke_on_reuse(raw) -> int` matches the presented string to an `OutstandingToken` that has a `BlacklistedToken` row, takes the user from that row (never from an unverified payload), blacklists every outstanding token of that user, logs a warning and returns the count; the serializer then answers 401. `revoke_sessions(user) -> int` is the same revoke-all, also exposed as `python manage.py revoke_sessions <email>`.
- URLs: `auth/login/`, `auth/refresh/`, `auth/logout/`, `auth/me/`.
- Tests: `tests/accounts/test_api.py` (login, wrong password 401, sixth attempt 429 with the cache cleared by a fixture, rotation rejects the used refresh token, logout blacklists, `/auth/me/`). `tests/test_auth_coverage.py` walks the resolver's `/api/v1/` patterns and asserts 401 without a token on every route except login and refresh, so a new endpoint that forgets authentication fails this test, not a review.

### 1.2 core services and queries

Section 4 covers `fx.py` and `set_exchange_rate`. Nothing else in `core` holds business rules.

### 1.3 employees

Model: SPEC section 5 "Employee". `related_name="compensation_records"` on the record's FK. Constraints `CheckConstraint(level BETWEEN 1 AND 6)` and `CheckConstraint(last_date IS NULL OR last_date >= joining_date)`, indexes as the table says plus `(department, country)`.

`employees/queries.py`:

| Function | Contract |
| --- | --- |
| `shown_record_subquery(on: date) -> QuerySet` | Live records of `OuterRef("pk")` annotated `is_current` (1 when current on `on`, else 0), ordered `-is_current, -effective_from`. `[:1]` of it is the shown record |
| `pick_shown(records: Sequence[CompensationRecord], on: date) -> CompensationRecord | None` | The Python twin of that ordering over a prefetched list. A test asserts the two agree on a fixture with current, scheduled, exited and cancelled rows |
| `shown_label(employee, record, on) -> str | None` | `None` when the record is current, `"exited <last_date>"` when `last_date < on`, `"from <effective_from>"` when the record is scheduled |
| `directory_queryset(on: date, reporting_currency: str, rates: fx.RateTable) -> QuerySet[Employee]` | The one query the 300 ms target depends on, below |
| `gross_bound(value: Decimal, side: Literal["min", "max"]) -> Decimal` | `value - 0.005` or `value + 0.005`, the tolerance from SPEC F4 |

The directory queryset:

```python
shown = shown_record_subquery(on)
qs = (
    Employee.objects.select_related("country", "department")
    .annotate(
        gross_local=Subquery(shown.values("gross_annual")[:1], output_field=DecimalField(14, 2)),
        gross=ExpressionWrapper(
            F("gross_local") * rates.case_expression(reporting_currency, "country__currency_code"),
            output_field=DecimalField(14, 2),
        ),
        status=Case(
            When(joining_date__gt=on, then=Value("upcoming")),
            When(last_date__lt=on, then=Value("exited")),
            default=Value("active"),
            output_field=CharField(),
        ),
    )
    .prefetch_related(
        Prefetch(
            "compensation_records",
            queryset=CompensationRecord.objects.filter(cancelled_at__isnull=True).order_by("-effective_from"),
            to_attr="live_records",
        )
    )
)
```

Why this shape. One correlated subquery per employee row, satisfied by the `(employee, effective_from)` index, gives `gross_local`. The rate is a `CASE WHEN country.currency_code = 'INR' THEN <Decimal> ...` expression built once per request from `RateTable`, so `gross` is one multiplication per row and SQLite can sort and range-filter 10,000 rows on it in one pass. The annotation is named `gross` so `?ordering=gross` and `?ordering=-gross` map onto it directly. Nothing else about the shown record is fetched in SQL: the page's records arrive through the prefetch (one query for the 25 to 100 employees on the page) and the serializer picks the shown one with `pick_shown`, which is the same rule. SQLite computes `gross` in floating point; it is used only to order and filter, and the displayed reporting-currency figure is `rates.convert(gross_local, ...)` in Python (SPEC section 4 rule 1). Range filters use `gross_bound`, so a value that SQLite rounds the other way is still inside the band. The `status` annotation makes the status filter a plain equality.

Query count for a list request: user lookup from the JWT, rates, count, page, prefetch. Five. Pinned with `django_assert_num_queries(5)` once measured. The detail endpoint is also five: user, rates, employee with its lookups, records, lines.

`employees/filters.py` has `DirectoryFilterSet(FilterSet)` with the exact parameter names of SPEC F4: `country`, `department` (both `CharInFilter` on `country__code`, `department__code`), `designation` (a `CharInFilter` with a `method` that matches each value case-insensitively, `designation__iexact`), `level` (`ChoiceInFilter`, values 1 to 6 so a stray value is a 400), `status` (`ChoiceFilter` on the annotation), `gross_min` and `gross_max` (`NumberFilter(method=...)` calling `gross_bound`), `joined_after` and `joined_before` (`DateFilter` on `joining_date` with `gte` and `lte`), and `ordering = OrderingFilter(fields=(("full_name", "full_name"), ("employee_code", "employee_code"), ("department__name", "department"), ("country__name", "country"), ("designation", "designation"), ("level", "level"), ("gross", "gross"), ("joining_date", "joining_date")))`. Default order `full_name, id` so pages are stable. `search` is DRF's `SearchFilter` over `full_name`, `employee_code`, `email`, subclassed as `core.filters.BoundedSearchFilter` to cap the terms at ten. A FilterSet maps parameters to lookups and holds no rules; the tolerance lives in `queries.gross_bound`.

`employees/services.py`:

| Function | Contract and exceptions |
| --- | --- |
| `next_employee_code() -> str` | The numeric part of the greatest existing `employee_code` plus one, formatted `ACME-NNNNNN`. Called inside the create transaction; `transaction_mode = IMMEDIATE` serialises writers so two creates cannot draw the same number |
| `create_employee(identity: dict, record: RecordInput, *, actor) -> Employee` | One transaction, with `validators.validate_identity` and `validators.validate_record` run inside it so SQLite's write lock covers the check (D44), `Invalid` on any error. A code the client names must be free (D44). Assigns the code when absent. Saves the employee with `created_at = updated_at = now`. Calls `compensation.services.add_first_record`. Writes audit `create` on the employee (`before = None`). Returns the employee; the view serialises it with the validators' warnings in a `warnings` list |
| `update_identity(employee, changes: dict, *, actor) -> Employee` | `employee_code` or `country_code` in `changes` raises `Invalid({"employee_code": ["employee_code cannot be changed"]})` (same for `country_code`). Inside one transaction: re-reads the employee, validates (a `joining_date` past the first record is a 400, D45), applies, sets `updated_at`, audit `update` with before and after snapshots |
| `exit_employee(employee, last_date: date, *, actor, today: date | None = None) -> Employee` | Inside one transaction, after re-reading the employee (D44), checks in this order: already exited, `Conflict("employee already exited on <date>")`; `last_date < joining_date`, `Invalid({"last_date": ["last_date precedes joining_date"]})`; any live record with `effective_from > today` and `effective_from > last_date`, `Conflict("scheduled revision on <date> must be cancelled before exit")`; the open record's `effective_from > last_date`, `Invalid({"last_date": ["last_date precedes the current record (effective <date>)"]})`. Then: `last_date` set, `compensation.services.close_open_record(employee, at=last_date + 1 day)`, `updated_at`, audit `exit` on the employee whose `after` snapshot shows the closed record. A future `last_date` passes the same checks and is a scheduled exit |

Serializers (`compensation/serializers.py` for the record input, `employees/serializers.py` for the rest), shape and types only:

- Input: `LineInputSerializer {component: code, annual_amount: Decimal}`, `RecordInputSerializer {effective_from?: date, bonus_annual?: Decimal (missing is zero), note: str = "", lines: [LineInput]}`, which refuses a component listed twice (`BASE appears twice in lines`, D46), `EmployeeCreateSerializer` (the body in SPEC section 8 for `POST /employees/`, a `RecordInputSerializer` plus the identity fields), `EmployeeIdentitySerializer` (identity fields, all optional, plus `employee_code` and `country_code` as optional fields so the service can reject them with 400 rather than the serializer silently dropping them), `ExitSerializer {last_date}`.
- Output: `EmployeeListSerializer` (id, employee_code, full_name, email, department `{code, name}`, designation, level, country `{code, name, currency_code}`, status, joining_date, last_date, `shown: {record_id, version, effective_from, effective_to, is_current, label, gross_local, currency_code, gross_reporting, reporting_currency}`). `EmployeeDetailSerializer` (the identity fields, `status`, `shown_label`, `current_record` as a full `CompensationRecordSerializer`, `created_at`, `updated_at`). `CompensationRecordSerializer` (id, employee id, version, effective_from, effective_to, is_current, is_scheduled, cancelled_at, cancelled_by email, currency_code, bonus_annual, gross_annual, net_annual, total_cost_annual, source, note, created_at, created_by email, `lines: [{component: code, annual_amount}]` with names and kinds read from `/meta/components/` on the client (D34), `converted: {currency, rate, rate_effective_from, bonus_annual, gross_annual, net_annual, total_cost_annual}`). `AuditEntrySerializer` (id, timestamp, actor email or null, action, entity_type, entity_id, before, after, import_batch). Converted figures come from `rates.convert` with the `RateTable` in the serializer context; the serializer calls `core/fx.py`, it computes nothing itself. Totals are read-only everywhere. The record and employee shapes follow the audit snapshots, datetimes included (`+00:00`, not DRF's `Z`), and `tests/audit/test_snapshots.py` holds them equal (D34).

Views (`employees/views.py`): `EmployeeListCreateView(ListCreateAPIView)` whose `get_queryset` parses `on` and `currency` (`fx.resolve_reporting_currency` with the `country` filter values), loads one `RateTable` for the request, and returns `directory_queryset`; `filterset_class = DirectoryFilterSet`, `search_fields` as above. `POST` calls `create_employee` and returns 201 with the detail shape plus `warnings`. `EmployeeDetailView(RetrieveUpdateAPIView)` for GET and PATCH, no PUT. `EmployeeExitView(GenericAPIView)` for POST. Writes answer with the detail shape read back through `detail_queryset`. `EmployeeAuditView(ListAPIView)` over `AuditLog.objects.filter(employee=...)`, newest first, paginated.

### 1.4 compensation

Models: SPEC section 5 "CompensationRecord" and "CompensationLine". Constraints on the record: `UniqueConstraint(employee, version)`, `UniqueConstraint(employee, effective_from, condition=Q(cancelled_at__isnull=True))` (live rows only, so a cancelled revision releases its date, D43), `UniqueConstraint(fields=["employee"], condition=Q(effective_to__isnull=True, cancelled_at__isnull=True), name="one_open_live_record")`, `CheckConstraint(effective_to IS NULL OR effective_to > effective_from)`, `CheckConstraint(bonus_annual >= 0)`. Indexes `(employee, effective_to)`, `(employee, effective_from)`, `gross_annual`. On the line: `UniqueConstraint(record, component)`, `CheckConstraint(annual_amount >= 0)`, `related_name="lines"`.

`compensation/services.py`:

```python
@dataclass(frozen=True)
class RecordInput:
    effective_from: date | None
    bonus_annual: Decimal
    note: str
    lines: Mapping[str, Decimal]          # component code -> annual amount

@dataclass(frozen=True)
class Totals:
    gross: Decimal
    net: Decimal
    total_cost: Decimal
```

| Function | Contract and exceptions |
| --- | --- |
| `compute_totals(lines, bonus_annual, components: Mapping[str, SalaryComponent]) -> Totals` | Pure. Section 3 gives the formulas. Unknown codes never reach it: the validators run first |
| `latest_record(employee)`, `open_record(employee)`, `current_record(employee, on)` | Read helpers over live records, `None` when absent |
| `add_first_record(employee, record: RecordInput, *, actor, source, batch=None, at=None) -> CompensationRecord` | Version 1, `effective_from` defaulting to `joining_date`, `effective_to = None`, `currency_code` from the country. Audit `revise` on the record with `before = None`, so a create writes one entry per entity (SPEC F2) |
| `revise(employee, record, *, actor, source, batch=None, at=None) -> CompensationRecord` | One transaction that re-reads the employee and runs `validators.validate_record(..., is_first=False)` under the write lock (D44), which answers `Conflict` for a revision dated after an exit (D36), then: the latest record's `effective_to` becomes the new `effective_from`; the new record gets `version = max(version) + 1` over all of the employee's records, cancelled ones included; totals from `compute_totals`; lines; audit `revise` with `before` the previous record's snapshot and `after` the new one. Section 3 has the dating rules |
| `cancel(record, *, actor, today=None) -> CompensationRecord` | Inside one transaction, on a fresh read of the row (D44): `Conflict("only a scheduled revision can be cancelled")` unless `cancelled_at IS NULL` and `effective_from > today`; `Conflict("the first record cannot be cancelled")` for version 1 (a future joiner's only record). Then `cancelled_at = now`, `cancelled_by = actor`; the previous live record's `effective_to` becomes the next live record's `effective_from`, else `last_date + 1` when the employee has a `last_date`, else `None`. Audit `cancel` with the record before and after |
| `close_open_record(employee, *, at: date) -> CompensationRecord` | Sets `effective_to = at` on the open live record. Caller has checked `at > effective_from`. Not audited on its own: the caller's `exit` entry carries it |
| `bulk_apply(entries: Sequence[BulkEntry], *, actor, source, batch=None, at: datetime, ctx: ValidationContext) -> BulkResult` | The entry point the seed and the import applier share, below |

`BulkEntry(employee: Employee | None, identity: dict | None, identity_changes: dict | None, last_date: date | None, records: list[RecordInput], ref: Any)`. A create carries `identity` and one or more records (the seed passes a whole history with explicit `effective_from` values). An update carries `employee` and `identity_changes`. A revise carries `employee`, one record and optional `identity_changes`. An exit carries `employee` and `last_date` with optional `identity_changes`. `ref` is handed back in `BulkResult` so the applier can match rows.

`bulk_apply` runs inside the caller's transaction and does, in order: validate every entry with the validators against `ctx` (an error raises `BulkInvalid(ref, messages)`; the seed never trips it and the applier has pre-validated); assign codes to creates without one; build `Employee` objects and `bulk_create(batch_size=1000)` (SQLite 3.35 and later return primary keys, so the objects are usable after the call); apply identity changes and exits to existing employees with `bulk_update`; build records with `chain_records` (each record's `effective_to` is the next one's `effective_from`, the last is open) and versions continuing from the employee's maximum, totals from `compute_totals`, closing the previous open record for revises and exits in one `bulk_update`; `bulk_create` the records, then the lines; build audit rows with `audit.snapshot_record` over the in-memory objects and `audit.bulk_record` them. Every batch is 1,000 objects. The single-row functions and the bulk path share `compute_totals`, the validators, `chain_records`, the version rule and the snapshot functions, and a test asserts that `revise()` and `bulk_apply()` given the same input produce the same rows apart from ids and timestamps.

`compensation/validators.py`: the one validator module (SPEC section 7, CLAUDE.md rule 4).

```python
Severity = Literal["error", "warning", "info"]

@dataclass(frozen=True)
class Message:
    field: str
    severity: Severity
    message: str

@dataclass
class NormalizedRow:            # one row of import, or one API call shaped like one
    row_number: int | None
    employee_code: str | None
    full_name, email, department, designation, level, country_code, gender
    joining_date, last_date, effective_from: date | None
    bonus_annual: Decimal | None
    amounts: dict[str, Decimal | None]       # component code -> amount, only columns present
    present: set[str]                        # columns that were non-blank
    parse_messages: list[Message]            # from the parser: bad numbers, bad dates
    # set by rules
    identity_changed: bool = False
    amounts_changed: bool = False
    noop: bool = False

@dataclass
class ValidationContext:        # built once per upload, per API call, per seed chunk; rules do no database access
    today: date
    countries: dict[str, Country]
    departments: dict[str, Department]
    components_by_country: dict[str, dict[str, SalaryComponent]]   # global ones merged into every country
    employees_by_code: dict[str, Employee]
    email_owner: dict[str, str]                 # lowercase email -> employee_code
    latest_by_employee: dict[int, CompensationRecord]
    open_by_employee: dict[int, CompensationRecord]
    scheduled_dates_by_employee: dict[int, list[date]]
    current_lines_by_employee: dict[int, tuple[CompensationRecord, dict[str, Decimal]]]
    country_median_gross: dict[str, Decimal]
    file_codes: Counter[str]; file_emails: Counter[str]
    first_row_of_code: dict[str, int]; first_row_of_email: dict[str, int]
```

Rules are `check_<name>(row, ctx) -> list[Message]`, registered in `RULES` in the order SPEC F1 fixes. The mapping to section 7 rows:

| Group (F1 order) | Functions | Section 7 rows |
| --- | --- | --- |
| Structure and types | `check_employee_code`, `check_email_format`, `check_country_exists`, `check_department_exists`, `check_level_range`, `check_gender_enum`, `check_parse_messages` (re-emits the parser's date and number messages), `check_base_required`, `check_bonus_non_negative`, `check_amounts_non_negative`, `check_components_applicable` | EmployeeID blank or malformed; email malformed; Unknown country_code; Unknown department; level; gender; date unparseable; comma decimal; more than two decimals; amount negative or non-numeric; BASE required; bonus_annual negative; component not applicable |
| Identity references | `check_email_in_use`, `check_code_available` (API create only, run before the rest, D44), `check_country_unchanged` | email already belongs to; employee_code already exists; country change not supported |
| Duplicates within the file | `check_duplicate_code`, `check_duplicate_email` | Duplicate EmployeeID in rows 41 and 388; Duplicate email in rows 12 and 90 (both rows get it) |
| Amounts changed | `check_identity_changed`, `check_amounts_changed` (set the flags; a new employee has both true) | the decision table in F1 |
| No-op | `check_noop` (info `No changes, row will be skipped on apply`, sets `row.noop`) | Row identical to the current record |
| Date rules (skipped when `row.noop`) | `check_last_date_after_joining`, `check_joining_before_first_record` (D45), `check_last_date_vs_open_record`, `check_last_date_cleared`, `check_last_date_vs_scheduled`, `check_effective_from_required`, `check_effective_from_after_joining`, `check_effective_from_after_latest`, `check_effective_from_defaulted` (info) | the seven `last_date` and `effective_from` rows, and joining_date after the first record |
| Warnings | `check_deductions_exceed_gross`, `check_gross_vs_country_bounds` | deductions exceed gross; gross below the minimum or above ten times the country median |

Header-level checks live in the same module so every message text has one home: `check_header(columns: list[str], component_codes: set[str]) -> HeaderResult(mapping, missing, unknown)` with the alias table, and `messages.py` beside it holds the templates (`MSG["date_invalid"] = "{field} is not a valid date: {value}"`) that the parser also uses. `validate_row(row, ctx) -> list[Message]` runs `RULES`. The API entry points build a `NormalizedRow` from plain values and run the same rules: `validate_identity(identity, ctx, employee=None)`, `validate_record(record, employee_or_country, ctx, *, is_first)`, `validate_exit(employee, last_date, ctx)`. Each raises `Invalid({field: [message]})` from the errors and returns the warnings for the response. `build_context(codes=..., emails=..., employees=...) -> ValidationContext` in `validators.py` does the queries, so the rules themselves never touch the database.

Serializers and views (`compensation/serializers.py`, `views.py`, `urls.py`): `CompensationHistoryView(ListCreateAPIView)` at `employees/<id>/compensation/`, GET returns the full history newest first as an unpaginated list (`pagination_class = None`, lines prefetched, `on` and `currency` honoured for `is_current` and `converted`), POST calls `revise` and returns 201 with the record and `warnings`. `CompensationRecordView(GenericAPIView)` at `compensation/<id>/`: DELETE calls `cancel` and returns 200 with the record. PATCH is P1 and is not registered.

### 1.5 imports

Models: SPEC section 5 "ImportBatch and ImportRow".

`imports/parser.py`:

| Function | Contract |
| --- | --- |
| `TEMPLATE_COLUMNS`, `REQUIRED_COLUMNS`, `ALIASES` | the twelve identity columns in order, the ten required ones, and the alias map (`employee_code`, `emp id`, `employee code` to `EmployeeID`, matched after lowercasing and removing spaces and underscores) |
| `open_rows(upload, file_name, content_type) -> Iterator[list]` | `.xlsx`: `openpyxl.load_workbook(upload, read_only=True, data_only=True)`, first worksheet, `iter_rows(values_only=True)`, closed in `finally`. `.csv`: decoded as `utf-8-sig`, `csv.reader`; `UnicodeDecodeError` raises `Invalid({"file": ["file is not UTF-8"]})`. Wrong extension or content type raises `Invalid({"file": [...]})` |
| `read(upload, ...) -> ParsedFile(header, rows: list[dict], row_count)` | Counts data rows while streaming, skipping rows whose cells are all blank. Past 10,000 it keeps counting without storing, then raises `Invalid({"rows": ["file has 10,450 data rows, limit 10,000"]})` |
| `parse_number(cell) -> Decimal | Message` | Numeric cells become `Decimal(str(value))`. Text: currency symbols and spaces stripped; a comma followed by exactly three digits with no dot anywhere is removed; any other comma is the separator error; more than two decimals is an error |
| `parse_date(cell) -> date | Message` | `date` and `datetime` cells (openpyxl gives `datetime`) become dates; text must be ISO `YYYY-MM-DD` |
| `normalize(raw: dict, mapping, components) -> NormalizedRow` | Applies the two parsers, lowercases the email, records `present` |

`imports/services.py`:

| Function | Contract |
| --- | --- |
| `stage_upload(upload, *, actor) -> ImportBatch` | Size over 10 MB raises `PayloadTooLarge` before anything is read. `check_header` first: missing required columns raise `Invalid({"missing_columns": [...], "unknown_columns": [...]})` and no batch exists. Otherwise the batch is created in `review` with `warnings = ["Ignored unknown column: Remarks", ...]`, `build_context` runs with the file's codes and emails (one query per lookup, `__in` chunks of 5,000), every row is normalised, validated and classified, `ImportRow` objects are built and `bulk_create(batch_size=1000)`, and `recount` sets the counts. Nothing touches `Employee` or `CompensationRecord` |
| `classify(row, ctx) -> str | None` | `None` when the code is unusable, `create` when unmatched, else the F1 decision table over `identity_changed`, `amounts_changed` and `effective_from`, adding the table's two error messages and `country change is not supported by import` where the table says so |
| `skip_row(batch, row, *, actor)`, `unskip_row(...)` | `Conflict` unless the batch is in `review`. Skip sets `status = skipped`; unskip restores `status` from `validation_status`. Both call `recount` |
| `discard(batch, *, actor)` | `review` to `discarded`, else `Conflict`. Not audited: no pay data changes |
| `recount(batch)` | One `aggregate` with conditional counts over the batch's rows |

`imports/applier.py`:

`approve(batch, *, actor, today=None) -> ImportBatch`. Refuses with `Conflict` when the batch is not in `review`, and with `Conflict("3 rows have errors", error_rows=3)` while unskipped error rows remain. Accepted rows are those with status `valid` or `warning` and action `create`, `update` or `revise`. Then:

```python
try:
    with transaction.atomic():
        ctx = validators.build_context(for_rows=accepted)          # fresh, from the live tables
        failures = {row.id: msgs for row in accepted if (msgs := validators.recheck_for_apply(row_as_normalized(row), ctx))}
        if failures:
            raise ReValidationFailed(failures)
        result = compensation.services.bulk_apply(build_entries(accepted, ctx), actor=actor, source="import", batch=batch, at=now, ctx=ctx)
        audit.record("import_apply", entity=batch, actor=actor, before=None, after=counts, import_batch=batch)
        mark approved: status, approved_at, created_rows, updated_rows, revised_rows, applied_rows, matched_employee on create rows
except ReValidationFailed as exc:        # outside the block, the rollback is complete
    rows get status = validation_status = "error" with the new messages, recount
    raise Conflict(f"{n} rows failed re-validation against current data", rows=[...])
except Exception as exc:
    batch.status = "failed"; batch.error_summary = f"{type(exc).__name__}: {exc}"[:2000]; save
    raise ApplyFailed(error_summary=batch.error_summary)
```

`recheck_for_apply` is the identity-reference, duplicate and date subset of `RULES`, run against a context rebuilt from the database so a revision added through the UI between upload and approve is seen. `build_entries` turns rows into `BulkEntry` values: a create row becomes identity plus one record; an identity-only row an update; a row with changed amounts a revise with any identity changes; a row whose `last_date` appeared or changed runs as an exit entry, which `bulk_apply` applies through the same rules as `exit_employee`. Audit entries per row follow SPEC F2: create rows write `create` on the employee and `revise` on the record, identity-only rows write `update`, revise rows write `revise` with the previous record as `before`, exit rows write `exit`; all carry `import_batch`. A row that changes identity fields or sets `last_date` as well as amounts writes its `update` or `exit` entry on the employee first and then the `revise` entry on the record, as the API path does. `updated_rows` still counts identity-only rows and `revised_rows` every row that produced a record, so the batch counts do not change.

`imports/template.py`: `build_template(country: str | None) -> bytes`, a write-only openpyxl workbook with one header row (the identity columns, then the component codes for that country in `sort_order`, or every component when omitted), the header frozen. Unknown country raises `Http404`.

`imports/management/commands/make_import_file.py`: arguments as SPEC section 11, `--seed` (default 42). Rows are template-shaped and come from the live tables: `--new N` invents employees with Faker, `--raises N` takes N existing employees with every amount raised 5 percent and `effective_from` the first of the month after the reference date, `--errors N` plants one of each error in turn (negative `BASE`, malformed email, unknown department, level 9, a `31/02/2024` date, a duplicate code, a comma decimal, `HRA` on a US row), `--all` writes every existing employee unchanged.

Serializers: `ImportBatchSerializer` (every column of the table), `ImportRowSerializer` (id, row_number, employee_code, full_name, status, validation_status, action, messages, matched_employee, normalized), `UploadSerializer {file}`. Views: `ImportListCreateView` (GET newest first, paginated; POST multipart, 201 with the batch), `ImportDetailView`, `ImportRowListView` (filters `status` comma-separated and `search` over `employee_code` and `full_name`, ordered by `row_number`, three queries), `ImportRowSkipView`, `ImportRowUnskipView`, `ImportApproveView`, `ImportDiscardView`, `ImportTemplateView` (`?country=`, `Content-Disposition: attachment; filename="acme-import-template-IN.xlsx"`). Uploads larger than Django's in-memory threshold land in a temporary file that Django removes after the request; the parser reads the stream and nothing is ever written under the project. Accepted content types: the xlsx type for `.xlsx`, `text/csv`, `application/csv` and `text/plain` for `.csv`, plus `application/octet-stream` when the extension is right.

### 1.6 insights

`insights/queries.py`:

```python
@dataclass(frozen=True)
class InsightFilters:
    country: tuple[str, ...]
    department: tuple[str, ...]
    include_exited: bool
    on: date
    currency: str          # "USD", "EUR", or the one country's local code
```

`population(f) -> QuerySet[CompensationRecord]` is the one predicate every insight shares:

```python
active  = Q(employee__joining_date__lte=on) & (Q(employee__last_date__isnull=True) | Q(employee__last_date__gte=on))
current = Q(effective_from__lte=on) & (Q(effective_to__isnull=True) | Q(effective_to__gt=on))
qs = CompensationRecord.objects.filter(cancelled_at__isnull=True)
if f.include_exited:
    exited_last = Q(employee__last_date__lt=on) & Q(effective_to__gt=F("employee__last_date"))
    qs = qs.filter((active & current) | exited_last)
else:
    qs = qs.filter(active & current)
# then employee__country__code__in and employee__department__code__in when given
```

Live records of one employee never overlap, so at most one is current on `on` and no subquery is needed. For an exited employee every earlier record ends on or before the last record's `effective_from`, which is on or before `last_date`, while the last record ends at `last_date + 1`; `effective_to > last_date` therefore selects exactly the last record. Future joiners fail `joining_date <= on`. A scheduled revision fails `effective_from <= on`.

Each insight is `def <name>(f: InsightFilters, rates: fx.RateTable) -> dict`, registered in `INSIGHTS`. Sums and counts: `population(f).values(<group fields>, "currency_code").annotate(n=Count("id"), total_cost=Sum("total_cost_annual"), gross_sum=Sum("gross_annual"))`, then in Python per group `total_cost = q2(sum(total_cost_ccy * rates.rate(ccy, f.currency)))` and `mean_gross = q2(sum(gross_sum_ccy * rate_ccy) / n)`. Medians and percentiles: `population(f).values_list("gross_annual", "currency_code", <group field>)`, each value converted as `q2(v * rate)`, then `statistics.median` and `statistics.quantiles(values, n=100, method="inclusive")` (p1 is index 0, p10 index 9, p25 index 24, p50 index 49, p75 index 74, p90 index 89, p99 index 98), each result passed through `q2`. Guards: zero values gives `None`; one value gives that value for every percentile. The small-group rule: any group with `n < 5` publishes `headcount` and `total_cost` only and `None` for mean, median and percentiles. Empty groups are listed with `headcount 0` and `None` elsewhere. Output shapes, with money as two-decimal strings after `core.money.render`:

| Insight | Shape |
| --- | --- |
| `summary` | `{currency, rate_month: {label, effective_from}, headcount, total_cost, mean_gross, median_gross, countries, departments}` |
| `by-country` | `{..., rows: [{country: {code, name}, headcount, total_cost, median_gross, share_pct}]}` sorted by `total_cost` descending, every country in the filter listed; `share_pct` is `total_cost / overall total_cost * 100` to one decimal |
| `by-department` | `{..., rows: [{department: {code, name}, headcount, total_cost, mean_gross, median_gross}]}` sorted by `total_cost` descending, all twelve listed |
| `distribution` | `{..., headcount, p1, p99, bands: [{index, from, to, count}], markers: {p10, p50, p90}}`. `width = (p99 - p1) / 12` unquantised; band `i` is `[p1 + i*width, p1 + (i+1)*width)`, the last band closed at `p99`; a value maps to `floor((v - p1) / width)` clamped to 0 and 11, so values outside `p1..p99` land in the end bands; `p1 == p99` gives one band `{from: p1, to: p1, count: n}`; under five people `bands` and `markers` are `None` |
| `by-level` | `{..., rows: [{level, headcount, min, p25, median, p75, max}]}` for levels 1 to 6; under five people all five figures are `None` (the general rule in SPEC section 9, D25) |
| `gender-gap` | `{..., rows: [{country: {code, name} | null, female: {headcount, median_gross}, male: {headcount, median_gross}, other_count, undisclosed_count, gap_pct, reason}]}`, one row per country in the filter and a final row with `country: null` for overall. `gap_pct = (median_male - median_female) / median_male * 100` to one decimal; `None` with `reason: "group too small"` when either gender has fewer than five people |

`rate_month` is `{label: rates.month_label(currency), effective_from}` where the month is that of the most recent `effective_from` among the rates used for the reporting currency; with `currency=local` the label is `"local currency (INR)"` and `effective_from` is `None`.

`insights/views.py`: `InsightView(APIView)`. Unknown name is 404. Parses `country` and `department` with `parse_csv`, `include_exited` with `parse_bool` (default false), `on` with `parse_on`, `currency` with `fx.resolve_reporting_currency`. Loads one `RateTable`, calls the query, returns `Response(render(payload))`. No DRF serializer: the shapes above are the contract and `frontend/src/api/types.ts` mirrors them. Queries per request: user, country lookup, rates, then one aggregate and at most one `values_list`. Four or five, pinned.

### 1.7 exports

`exports/writers.py`: `escape_cell(value)` prefixes a single quote when a text cell starts with `=`, `+`, `-`, `@`, tab or carriage return (numbers are written as numbers and are never escaped); `csv_stream(header, rows) -> Iterator[bytes]` writes one row at a time with `csv.writer`, UTF-8 with a BOM so Excel opens it correctly; `xlsx_bytes(header, rows) -> bytes` uses a write-only workbook and `ws.append`; `json_bytes(keys, rows) -> bytes`.

`exports/tables.py`: `directory_table(request) -> (header, keys, rows)` builds the same queryset as the directory view (`directory_queryset` with the request's `on` and `currency`), applies `DirectoryFilterSet` and `SearchFilter` to it the way the list view does, and iterates with `.iterator(chunk_size=1000)` (prefetches are honoured chunk by chunk), yielding the sixteen columns of SPEC F6 in order; `INSIGHT_TABLES = {"summary": ..., "by-country": ..., "by-department": ..., "distribution": ..., "by-level": ..., "gender-gap": ...}`, each turning the insight dict into `(header, keys, rows)` with the row shapes SPEC F6 names.

`exports/views.py`: `ExportEmployeesView` and `ExportInsightView` (`APIView`). `file` must be `csv`, `xlsx` or `json`, else 400. CSV is a `StreamingHttpResponse`; XLSX and JSON are built in memory (a 10,000-row XLSX is a few megabytes). `Content-Disposition: attachment; filename="acme-employees-20261007-0930.csv"`, the timestamp in UTC. JSON is `{"generated_at", "filters": {the query parameters}, "rows": [{key: value}]}` with snake_case keys (D27). Unknown insight name is 404.

### 1.8 audit

Model: SPEC section 5 "AuditLog". `entity_type` values: `employee`, `compensation_record`, `import_batch`, `exchange_rate`.

`audit/services.py`: `record(action, *, entity, actor, before, after, employee=None, import_batch=None, at=None) -> AuditLog` (`at` defaults to now; the seed passes the reference datetime); `bulk_record(entries: list[AuditLog]) -> None` in chunks of 1,000; `snapshot_employee(employee, shown_record=None) -> dict` and `snapshot_record(record, lines=None) -> dict`. The snapshots mirror the detail serializers field for field, minus the request-dependent keys (`converted`, `is_current`, `is_scheduled`, `shown_label`, `status`), rendered JSON-safe with `core.money.render`. They are plain functions rather than DRF serializer calls so the seed can produce 40,000 of them inside its 60 s budget, and `tests/audit/test_snapshots.py` asserts `snapshot_record(r) == CompensationRecordSerializer(r, context=...).data` minus those keys, so the two cannot drift. Converted amounts never enter an audit row (rule 3).

### 1.9 seed

Section 5.

## 2. Import pipeline

```mermaid
sequenceDiagram
  participant B as Browser
  participant V as imports/views.py
  participant S as imports/services.py
  participant P as imports/parser.py
  participant VA as compensation/validators.py
  participant A as imports/applier.py
  participant C as compensation/services.py
  participant AU as audit/services.py
  participant DB as SQLite
  B->>V: POST /api/v1/imports/ (multipart, bearer)
  V->>S: stage_upload(upload, actor)
  S->>S: size over 10 MB raises 413
  S->>P: read(upload): header, rows, row_count
  P-->>S: rows, or 400 for encoding, extension, row limit
  S->>VA: check_header(columns)
  alt required column missing
    S-->>V: Invalid {missing_columns, unknown_columns}
    V-->>B: 400, no batch created
  end
  S->>DB: INSERT ImportBatch(status=review, warnings)
  S->>DB: build_context: countries, departments, components, matched employees, their records and lines, emails in use
  loop every data row
    S->>P: normalize(raw)
    S->>VA: validate_row(row, ctx)
    S->>S: classify(row, ctx) -> create, update, revise, noop or None
  end
  S->>DB: bulk_create ImportRow in chunks of 1,000, recount
  V-->>B: 201 batch summary
  B->>V: POST rows/{rowId}/skip/ or unskip/
  V->>S: skip_row or unskip_row (409 unless review), recount
  B->>V: POST /imports/{id}/discard/
  V->>S: discard (409 unless review)
  B->>V: POST /imports/{id}/approve/
  V->>A: approve(batch, actor)
  A->>A: 409 unless review, 409 while unskipped error rows remain
  A->>DB: BEGIN IMMEDIATE (transaction.atomic)
  A->>VA: build_context from the live tables, recheck_for_apply on every accepted row
  A->>C: bulk_apply(entries, source=import, batch)
  C->>VA: validate every entry
  C->>DB: bulk_create employees, records, lines; bulk_update closed records and identity changes
  C->>AU: bulk_record create, update, revise and exit entries with import_batch
  A->>AU: record(import_apply, batch, after=counts)
  A->>DB: batch approved, counts, COMMIT
  alt re-validation failed
    DB-->>A: ROLLBACK
    A->>DB: rows re-marked error, recount, batch stays in review
    V-->>B: 409 with the rows
  else any other exception
    DB-->>A: ROLLBACK
    A->>DB: batch failed with error_summary, rows kept
    V-->>B: 409 with error_summary
  end
  V-->>B: 200 batch summary
```

Memory at the peak: 10,000 `NormalizedRow` and `ImportRow` objects live at once before the chunked `bulk_create`, each with two JSON blobs; tens of megabytes, measured by `/perf-timing` in step 5 against the 1 GB machine.

## 3. Compensation revisions and totals

Totals, computed by `compute_totals` from the lines and the bonus, in local currency:

```
gross_annual      = q2( sum(annual_amount for lines whose component.kind == "earning") + bonus_annual )
net_annual        = q2( gross_annual - sum(annual_amount for kind == "deduction") )
total_cost_annual = q2( gross_annual + sum(annual_amount for kind == "employer_contribution") )
```

Inputs are already two-decimal `Decimal` values, so the sums are exact and `q2` is a guarantee rather than a rounding. Monthly figures are the annual figure divided by 12, formatted in the browser, never stored. Nothing arrives at `compute_totals` as a float: serializers parse `DecimalField(max_digits=14, decimal_places=2)`, the parser builds `Decimal(str(cell))`, and the seed draws its noise with `random` then converts the final figure through `Decimal(str(round(x)))`.

Quantisation rule. Rates are multiplied unquantised; a converted single amount is `q2(amount * rate)`. A converted sum is `q2(sum_local * rate)`, not a sum of converted rows. A mean is `q2(converted_sum / n)`. Medians and percentiles run over per-person values that were each `q2`-converted, and the statistic is `q2`-ed again. Percentages (`share_pct`, `gap_pct`) are quantised to one decimal. These are the only rounding points.

Dating rules:

1. Intervals are half-open. A record covers `[effective_from, effective_to)`; `effective_to` is `None` for the latest live record. Only `revise`, `cancel`, `close_open_record` and `bulk_apply` ever write `effective_to`.
2. A new revision's `effective_from` must be strictly after the latest record's `effective_from` (rule `effective_from must be after 2025-04-01 (latest record)`), on or after `joining_date`, and the previous record's `effective_to` becomes exactly that date. A next-day revision is therefore legal and leaves the previous record one day long.
3. `version` is the employee's maximum plus one, cancelled rows included, so a version number is never reused and history keeps its numbering.
4. A revision dated after today is scheduled: `current_record(employee, today)` still returns the earlier one, and the scheduled one is the latest and the open one.
5. Cancel marks a scheduled live record and re-chains its predecessor: the previous live record's `effective_to` becomes the next live record's `effective_from`, else `last_date + 1` when the employee has a `last_date` (a scheduled exit must keep the history closed), else `None`. Several scheduled revisions may exist; cancelling the middle one re-chains its neighbours. A cancelled record releases its date: the unique `(employee, effective_from)` covers live rows only, so the same date can be entered again, and history breaks the tie by version (D43).
6. Exit closes the open live record at `last_date + 1 day` after the checks in 1.3. A future `last_date` is a scheduled exit and closes the record immediately with a future `effective_to`.
7. Once a record has been current its amounts, lines, `effective_from`, `bonus_annual` and `note` are never written again. The P1 in-place correction endpoint is not built.
8. An exited employee's history ends at `last_date + 1`: a revision dated after `last_date` is a 409 through the API, the import and the seed, and a revision dated on or before it is allowed and ends at `last_date + 1` (D36, pending the owner's answer at the step 2 close).

Immutability is enforced in the services, which only ever `save(update_fields=["effective_to"])` or set `cancelled_at` and `cancelled_by` on an existing record.

## 4. FX

`core/fx.py`:

```python
@dataclass(frozen=True)
class Rate:
    from_currency: str; to_currency: str; rate: Decimal; effective_from: date

class RateTable:
    @classmethod
    def load(cls, on: date) -> "RateTable"
    def rate(self, from_currency: str, to_currency: str) -> Decimal
    def effective_from(self, from_currency: str, to_currency: str) -> date | None
    def convert(self, amount: Decimal, from_currency: str, to_currency: str) -> Decimal
    def case_expression(self, to_currency: str, currency_field: str) -> Case
    def month_label(self, to_currency: str) -> str
    def rows(self) -> list[dict]

def resolve_reporting_currency(currency: str | None, country_codes: Sequence[str], countries: Mapping[str, Country]) -> str
```

- `load(on)` reads every `ExchangeRate` row in one query and keeps, per pair, the row with `effective_from <= on < effective_to` (or open), else the row with the smallest `effective_from`. That is SPEC section 4 rule 4: a month per row, the earliest rate before the first month, no 422.
- `rate(a, b)`: `1` when `a == b`; the direct row when the pair exists; otherwise through USD: `rate(a, "USD") * rate("USD", b)`, where a missing `USD -> b` row falls back to `1 / rate(b, "USD")`. Nothing is quantised here. A pair that cannot be resolved raises `MissingRate`, a `DomainError` mapped to `400 {"currency": [...]}`; it is unreachable with the seeded pairs and exists so the failure is explicit.
- `effective_from(a, b)`: `None` for identity, the row's date for a direct pair, the later of the two legs for a routed one.
- `convert(amount, a, b) = q2(amount * rate(a, b))`.
- `case_expression(to, field)`: `Case(*[When(**{field: ccy}, then=Value(self.rate(ccy, to))) for ccy in currencies], default=Value(Decimal("1")), output_field=DecimalField(18, 8))`, built from the six seeded currencies. Used only by the directory annotation to order and filter.
- `month_label(to)`: "October 2026 rates" from the most recent `effective_from` among the rates feeding `to`; for a local currency, "local currency (INR)".
- `resolve_reporting_currency`: `usd` or `None` gives `USD`, `eur` gives `EUR`, `local` gives the one filtered country's `currency_code` and raises `Invalid({"currency": ["currency=local needs exactly one country in the filter"]})` for any other count; anything else is `Invalid`.

`set_exchange_rate(from_currency, to_currency, rate, effective_from, *, actor=None, replace=False) -> ExchangeRate` in `core/services.py`, used by the management command and `ensure_rates`: `effective_from.day != 1` raises `Invalid({"effective_from": ["must be the first day of a month"]})`; `rate <= 0` or identical currencies raise `Invalid`; with an open row for the pair, a date before it raises `Invalid({"effective_from": ["on or before the latest row 2026-10-01"]})`; the same date raises `Invalid({"effective_from": ["a rate for October 2026 exists, pass --replace"]})` unless `replace`, in which case the existing row's `rate` is updated; otherwise, in one transaction, the open row's `effective_to` becomes the new date, the new row is inserted open-ended, and audit `set_rate` is written on the new row with the closed row's snapshot as `before`. The command is `set_exchange_rate FROM TO RATE --effective-from YYYY-MM-01 [--replace]`.

Where conversion happens: the directory annotation (`case_expression`, for ordering and filtering only), the list and detail serializers (`convert` per shown record), the insight queries (section 1.6), and the export tables (the same serializers' values). Never in a model, never stored.

## 5. Seed

`seed/profiles.py` holds every design parameter from SPEC section 11 as plain data: `COUNTRIES` (code, name, currency, share, level-3 anchor, minimum gross, the country's components with their share of base, employer contribution share), `DEPARTMENTS` (code, name, share, pay multiplier), `LEVELS` (share, multiplier), `DESIGNATIONS[(department, level)]`, `TAX_BANDS` (levels 1 to 2 at 10 percent of gross, 3 to 4 at 20, 5 to 6 at 30), `BONUS` (share of employees, range 5 to 15 percent of base, country weights), `GENDER` (48, 50, 2), `JOINING_RANGE` (2015-01-01 to 2026-09-30), `EXIT_SHARE` (8 percent), `RAISE_RANGE` (4 to 12 percent), `REFERENCE_DATE = date(2026, 10, 6)`, `REFERENCE_DATETIME = datetime(2026, 10, 6, tzinfo=UTC)`, `RATES` (sixteen rows), and `NOISE_SIGMA = 0.18`.

Seeded rates, design parameters and not sourced:

| Pair | September 2026 | October 2026 |
| --- | --- | --- |
| INR to USD | 0.01195 | 0.01200 |
| GBP to USD | 1.3410 | 1.3450 |
| EUR to USD | 1.1720 | 1.1750 |
| SGD to USD | 0.7790 | 0.7810 |
| INR to EUR | 0.01020 | 0.01021 |
| GBP to EUR | 1.1440 | 1.1447 |
| USD to EUR | 0.8530 | 0.8511 |
| SGD to EUR | 0.6650 | 0.6647 |

The random stream is one `random.Random(seed)` instance passed everywhere, and one `Faker(locale)` per country locale (`en_IN`, `en_US`, `en_GB`, `de_DE`, `nl_NL`; Singapore draws from `en_US` because Faker has no Singapore locale, D35) seeded with `fake.seed_instance(seed)`; the generator never reads the global `random`, never iterates a set or dict in insertion-insensitive order, and draws values for each employee in a fixed sequence (country, department, level, gender, name, joining date, exit, bonus, base noise, raises). Emails are `f"{first}.{last}.{n}@acme.example"` lowercased with a running number, so they are unique by construction. Codes are `ACME-000001` upwards in generation order.

Generation per employee (`seed/generator.py`, `generate(n, rng) -> Iterator[BulkEntry]`): country by weighted share, department, level, gender, designation from the table; `base = anchor * level_multiplier * department_multiplier * rng.lognormvariate(0, 0.18)` rounded to the nearest 100 units of local currency; each component as its share of base (or of gross for `TAX`) times a per-employee jitter drawn uniformly between 0.95 and 1.05, rounded to whole units (D35); bonus for about a third of employees weighted toward US, GB and DE; `joining_date` uniform over the range; 8 percent exited with `last_date` uniform between `joining_date + 30 days` and the reference date; the record history is the joining record followed by a raise on every 1 April strictly after `joining_date` and on or before the earlier of `last_date` and the reference date, each raise multiplying base by `1 + r` with every component recomputed, and the history trimmed to the joining record plus the three most recent raises (the joining record then runs until the first kept raise, and kept raises carry their compounded amounts). Records are chained half-open and an exited employee's last record ends at `last_date + 1`. No seeded record is cancelled.

`seed_data` (`seed/management/commands/seed_data.py`): arguments as SPEC section 11. The flow is `ensure_lookups`, `ensure_rates`, the HR Manager (`hr@acme.example`, `SEED_ADMIN_PASSWORD`, required when `DEBUG` is off, `change-me` otherwise), then `bulk_apply` per chunk of 1,000 generated entries with `source="seed"`, `actor=None`, `at=REFERENCE_DATETIME`, inside one `transaction.atomic()` for the whole run. `--if-empty` exits 0 without writing when `Employee` has rows; no flag on a non-empty database is an error; `--reset` first truncates the business tables (`AuditLog`, `CompensationLine`, `CompensationRecord`, `ImportRow`, `ImportBatch`, `Employee`, `ExchangeRate`, `SalaryComponent`, `Department`, `Country`) in dependency order and deletes their `sqlite_sequence` entries so ids restart at 1. `reset_demo` is `--reset` with the fixed arguments (`--employees 10000 --seed 42`) and keeps users. These two commands are the only code that deletes rows (CLAUDE.md rule 6). Timestamps (`created_at`, `updated_at`, audit `timestamp`) are set to `REFERENCE_DATETIME` by passing `at`, so the determinism scope holds across runs and machines.

Determinism test (`tests/seed/test_seed.py`, marked `slow`): seed 500 employees with seed 42 into the test database, dump the eight business tables to canonical CSV (tables in a fixed order, rows by primary key, columns in model field order, `Decimal` as text with the field's scale, dates ISO, JSON with `sort_keys=True` and `separators=(",", ":")`), hash with SHA-256 and compare to `tests/seed/golden.txt`. Then run `--reset` on the same database and compare again, which proves the `sqlite_sequence` reset. A change to `profiles.py` is expected to change the hash; the commit that changes it regenerates the file and says so in its body. The same test asserts the shares (countries within 2 points, levels, gender), the one-open-record invariant, that exited employees' records end at `last_date + 1`, and `--if-empty` behaviour. Seed timing is recorded by `/perf-timing` on the 10,000-row run, target under 60 s.

## 6. Frontend

Routes (`src/router.tsx`, `createBrowserRouter` from `react-router`, `RouterProvider` from `react-router/dom`; v8 dropped `react-router-dom`):

| Route | Page component | Layout | Data |
| --- | --- | --- | --- |
| `/login` | `pages/Login` | none | `useLogin` mutation |
| `/` | `pages/Dashboard` | `AppShell` behind `RequireAuth` | six `useInsight(name, filters)` queries, `useExchangeRates` |
| `/employees` | `pages/Employees` | `AppShell` | `useEmployeeList(params)` |
| `/employees/new` | `pages/NewEmployee` | `AppShell` | `useComponents(country)`, `useCreateEmployee` |
| `/employees/:id` | `pages/EmployeeDetail` | `AppShell` | `useEmployee(id)`, `useCompensationHistory(id)`, `useAudit(id)`, mutations revise, cancel, exit, update |
| `/imports` | `pages/Imports` | `AppShell` | `useImportList(page)`, `useUploadImport` |
| `/imports/:id` | `pages/ImportReview` | `AppShell` | `useImportBatch(id)`, `useImportRows(id, params)`, mutations skip, unskip, approve, discard |
| `*` | `pages/NotFound` | `AppShell` | none |

Component tree:

```
App
  ThemeProvider (lib/theme) + CssBaseline
  QueryClientProvider
  SessionGate               bootstraps the session once (refresh if a token exists), then renders the router
    RouterProvider
      Login
      RequireAuth -> AppShell (left nav: Dashboard, Employees, Imports; top bar: page title, user email, Sign out)
        Dashboard: PageHeader, FilterBar(dashboard), RateMonthLabel, KpiRow(KpiCard x4), InsightGrid(ByCountryCard, ByDepartmentCard, DistributionCard, ByLevelCard, GenderGapCard), each InsightCard(title, question, ExportMenu, children)
        Employees: PageHeader(actions: Add employee, ExportMenu), FilterBar(directory), SearchField, ServerGrid(columns.directory), EmptyState, ErrorState
        NewEmployee: PageHeader, EmployeeForm(identity fields, country select, RecordLinesFields(components for the country), bonus, effective_from, note)
        EmployeeDetail: PageHeader(employee name, code, StatusChip, actions: Edit, Add revision, Mark exited), CurrentRecordCard(lines table, local and reporting columns, shown label), HistoryList(RecordRow x n, cancelled rows greyed with "cancelled", Cancel button on scheduled rows), AuditTab(AuditList), EditIdentityDialog, RevisionDialog, ExitDialog, CancelConfirm
        Imports: PageHeader(Download template menu by country), UploadDropzone, BatchList(BatchRow with StatusChip and counts, warnings), EmptyState
        ImportReview: PageHeader(file name, StatusChip, actions: Approve (disabled with reason tooltip), Discard, Download template), BatchSummaryStrip, StatusFilter, SearchField, ServerGrid(columns.importRows with RowMessagesCell and SkipToggle), EmptyState
```

API layer (`src/api/`): `client.ts` exports `apiFetch<T>(path, {method, body, query})` which prefixes `/api/v1`, serialises `query` (arrays joined with commas, `undefined` dropped), sets the bearer header and `Content-Type: application/json` unless the body is `FormData`, parses JSON, and throws `ApiError {status, data}` with a `fieldErrors()` helper. On 401 it awaits `refreshOnce()`, a module-level promise shared by every concurrent caller so only one refresh is in flight, retries the request once, and on a second 401 clears the session and calls the registered `onUnauthenticated` which navigates to `/login?next=<current path>`. `types.ts` holds hand-written types mirroring the serializer and insight shapes; money fields are `string` and only chart adapters call `Number()`. `keys.ts`:

```ts
export const keys = {
  me: ['auth', 'me'],
  meta: { countries: ['meta', 'countries'], departments: ['meta', 'departments'],
          components: (country: string) => ['meta', 'components', country],
          rates: (on?: string) => ['meta', 'rates', on ?? 'today'] },
  employees: { all: ['employees'], list: (p: ListParams) => ['employees', 'list', p],
               detail: (id: number) => ['employees', id],
               history: (id: number, p: HistoryParams) => ['employees', id, 'compensation', p],
               audit: (id: number) => ['employees', id, 'audit'] },
  imports: { all: ['imports'], list: (page: number) => ['imports', 'list', page],
             detail: (id: number) => ['imports', id],
             rows: (id: number, p: RowParams) => ['imports', id, 'rows', p] },
  insights: { all: ['insights'], one: (name: string, f: InsightParams) => ['insights', name, f] },
};
```

Every parameter object is part of the key, so a filter change is a new query. List queries use `placeholderData: keepPreviousData` so a grid keeps its rows while the next page loads. Meta queries have `staleTime` of five minutes, everything else the default. Invalidation after mutations: create employee invalidates `employees` and `insights`; identity update, revise, cancel and exit invalidate `['employees', id]` (detail, history and audit share the prefix), `['employees', 'list']` and `insights`; skip and unskip invalidate `['imports', id]`; approve invalidates `['imports', id]`, `employees` and `insights`; discard invalidates `['imports', id]` and `['imports', 'list']`.

Session (`src/lib/auth.ts`): the access token lives in a module variable exposed through a tiny `useSyncExternalStore` store; the refresh token lives in `localStorage` under `acme.refresh` (DECISIONS D21). `setSession`, `clearSession`, `getAccessToken`, `bootstrap()` (one refresh on load when a refresh token exists, otherwise unauthenticated). A refresh runs inside `navigator.locks.request('acme-refresh', ...)` and reads the stored token inside the lock, so two tabs never present the same token (the second presentation would revoke every session, D21); where `navigator.locks` is missing (jsdom) the per-tab single-flight promise stands in. A refused refresh clears the session only while `localStorage` still holds the refused token; if another tab has rotated it meanwhile, the newer token is tried once. `Sign out` posts the refresh token to `/auth/logout/`, clears the session and navigates to `/login`.

Grid adapter (`src/components/grid/serverModel.ts`), pure and unit-tested:

```ts
toListParams({ paginationModel, sortModel, filters, search }): ListParams
  // page = paginationModel.page + 1, page_size = pageSize,
  // ordering = sortModel[0] ? (sort === 'desc' ? '-' : '') + sortField[field] : undefined
fromSearchParams(sp: URLSearchParams): GridState     // page, page_size, ordering, search and every filter
toSearchParams(state: GridState): URLSearchParams    // drops defaults and empties so URLs stay short
```

`ServerGrid` wraps `DataGrid` with `paginationMode="server"`, `sortingMode="server"`, `filterMode="server"`, `disableColumnFilter`, `pageSizeOptions={[25, 50, 100]}`, `rowCount` taken from the query's data, which `placeholderData: keepPreviousData` keeps defined during a refetch (an `undefined` count would reset the page), `paginationModel` and `sortModel` controlled from the URL state, `loading`, `density="compact"`, keyboard navigation left at MUI defaults, and the grid's own column chooser enabled through the toolbar. Directory columns: code, name, email (hidden by default), department, country (the name, since the API orders by name), designation, level, status (chip), record (the shown record's label written out: `current`, `from 1 Jan 2027`, `exited 30 Jun 2026`), gross local, gross reporting, joining date, last date (hidden), effective from, version (hidden); the pagination and sort models handed to the grid are memoised on the URL values, because a fresh model each render makes the grid re-apply it and reset the page; money columns are `type: 'number'` with a `valueFormatter` calling `formatMoney`. Import review columns: row, status chip, action chip, EmployeeID, name, then one column per template column; a cell whose field has a message gets the severity tint and a tooltip with the message text, and a trailing Messages column lists them; the last column is the skip toggle.

FilterBar (`src/components/filters/`): `useUrlFilters()` reads and writes `useSearchParams` for the directory's keys (the dashboard gets its own hook over its own keys in step 6), so filters, page, sort and search survive reloads and are shareable links. The directory keys are `country`, `department`, `designation`, `level`, `status`, `gross_min`, `gross_max`, `joined_after`, `joined_before`, `currency`, `search`, `page`, `page_size`, `ordering`. The dashboard keys are `country`, `department`, `currency`, `include_exited`. Changing any filter resets `page` to 1. The currency select offers `USD`, `EUR`, and `Local` only while exactly one country is selected; when the country selection changes away from one country and `currency` is `local`, the hook rewrites it to `usd`, and a URL that arrives that way is read the same. The designation field is free text, matched exactly but case-insensitively, since titles have no lookup endpoint (D40). The UI never sends `on`: the reporting-date picker is P1 and the API defaults to today.

Formatters (`src/lib/money.ts`, `src/lib/dates.ts`): `formatMoney(value: string, currency: string, { fraction = 0 })` uses `Intl.NumberFormat('en-US', { style: 'currency', currency, currencyDisplay: 'code', minimumFractionDigits, maximumFractionDigits })` and gives `INR 1,450,000`; grids and charts use whole units, detail lines and forms two decimals; `formatCompact` gives `USD 1.2M` for axes; `monthly(value)` divides by 12 for the "per month" line on the detail card; `formatDate` gives `7 Oct 2026` (`en-GB`, medium); `formatDateTime` for audit timestamps. Codes are always shown with the number, never a symbol, because six currencies sit in one grid.

Forms (`src/components/forms/`): `react-hook-form` with `zodResolver`; `schemas.ts` mirrors the input serializers (`employeeCreateSchema`, `identitySchema`, `revisionSchema`, `exitSchema`), with amounts as strings matching `/^\d+(\.\d{1,2})?$/` so no float arithmetic happens in the browser; `applyServerErrors(error, setError)` maps `{field: [message]}` onto fields (`lines.<code>` onto the line input) and `detail` onto a form-level alert; validation runs on blur and the submit button is never disabled for an invalid form, the error summary is announced instead. `RecordLinesFields` renders one amount input per component of the chosen country from `useComponents(country)`, grouped by kind, with the computed preview of gross, net and total cost done with `Number()` purely for display and labelled "preview".

Error and empty states, one sentence that says what to do next:

| Where | Text |
| --- | --- |
| Directory, filters match nothing | "No employees match these filters. Clear a filter or change the search." |
| Directory, no data at all | "No employees yet. Import a spreadsheet or add an employee." |
| Imports, none yet | "No imports yet. Download the template, fill it in and drop it here." |
| Review grid, status filter empty | "No rows with this status. Choose another status." |
| Employee not found | "This employee does not exist. Go back to the directory." |
| Dashboard, empty population | "No one matches these filters today. Clear a filter." (KPIs show 0) |
| Any failed load | "Could not load <thing>. Check your connection and try again." with a Retry button that refetches |
| Approve disabled | tooltip "3 rows have errors. Skip them or fix the spreadsheet and upload again." |
| Login failure | "Email or password is wrong." and on 429 "Too many attempts. Wait a minute and try again." |

A 400 maps onto fields, a 409 shows the server's `detail` in an inline alert beside the action that caused it, a 401 goes through the refresh path, anything else shows the failed-load state.

## 7. Visual direction

The product is a ledger for one HR manager who reads six currencies all day, so the numbers are the design. Everything else steps back: a cool paper background with white cards, one ink for text, one restrained ink blue for actions, hairline rules instead of card shadows, and one sans-serif family, IBM Plex Sans, set with tabular figures wherever a number appears so columns of money align to the digit. Money is written as `INR 1,450,000` with the code in a lighter weight beside the figure, never a symbol, which is the one deliberate stylistic move in the interface and it exists because a symbol is ambiguous across six countries. Status is a small tinted chip with text, never colour alone. Density is compact in the two large grids and standard everywhere else. There is no decorative motion: the only animations are MUI's own on dialogs and menus, and they are off under `prefers-reduced-motion`. Charts follow the dataviz mark specs: bars no thicker than 24 px with a 4 px rounded data end and a square baseline, a 2 px surface gap between adjacent bars, hairline gridlines, axis text in muted ink, tooltips on every mark, labels placed sparingly (a share on each country bar, the value at the tip of each department bar, the gap figure above each gender pair), and a legend only on the one chart with two series. Light theme only in v1 (D28).

Tokens (`src/lib/theme.ts`, `createTheme({ cssVariables: true, ... })`):

| Token | Value | Use |
| --- | --- | --- |
| `paper` | `#F4F5F1` | app background |
| `surface` | `#FFFFFF` | cards, grids, dialogs, chart surface |
| `ink` | `#1C2430` | primary text, 15.6:1 on surface |
| `ink.secondary` | `#4F5965` | secondary text, 7.1:1 |
| `ink.muted` | `#646C78` | captions, axis text, 4.8:1 on paper |
| `rule` | `#DCE0D8` | borders, dividers, gridlines |
| `primary` | `#2F4A7A` | buttons, links, focus ring, selected nav; white on it 8.8:1 |
| `primary.dark` | `#223760` | hover |
| `status.success` | text `#1B6B3A` on `#E3F1E7` | valid rows, active employees, approved batches (5.6:1) |
| `status.warning` | text `#8A5A00` on `#FBF0D9` | warning rows (5.2:1) |
| `status.error` | text `#A32A1F` on `#FBE4E1` | error rows, failed batches, field errors (5.9:1) |
| `status.info` | text `#35559A` on `#E4EAF7` | scheduled revisions, upcoming joiners, batches in review (6.0:1) |
| `status.neutral` | text `#5B6470` on `#ECEEF1` | skipped, no-op, cancelled, exited, discarded (5.2:1) |
| `series.1` | `#2A78D6` | every single-series chart, the female bars |
| `series.2` | `#EB6834` | the male bars |
| `chart.grid` | `#E3E6E0` | hairline gridlines |
| `chart.marker` | `#646C78` | p10, p50 and p90 reference lines |
| font | IBM Plex Sans 400, 500, 600 via `@fontsource/ibm-plex-sans`; `font-variant-numeric: tabular-nums` on `.num`, grid cells of type number, KPI figures and axis ticks | |
| type scale | 12 / 14 / 16 / 20 / 24 / 32 px with line heights 16 / 20 / 24 / 28 / 32 / 40; body 14, page title 24 weight 600, card title 16 weight 600, KPI figure 32 weight 500 with the currency code at 14 | |
| spacing | 4 px base; 8, 12, 16, 24, 32 | |
| radius | 6 px on cards, inputs and chips; 4 px on chart data ends | |
| focus | 2 px solid `primary` outline with 2 px offset on every focusable element | |

The series pair was run through the dataviz validator on the white surface and passes every check (adjacent CVD ΔE 24.7, normal-vision ΔE 33.6, both above 3:1 contrast). The UI token ratios above were computed with the WCAG formula; every text token clears 4.5:1 on the surface it is used on.

Skills used and what each contributed. `ui-ux-pro-max` (searches on typography, colour, UX and charts): the candidate typefaces with tabular figures for data-dense dashboards, the formal neutral-plus-status-chip palette shape, the empty-state and inline-validation rules, the focusable error summary, and the bar-chart guidance (sort by value, direct labels, never colour alone, a table alternative, which the export menu provides). `frontend-design` plugin: the brief-grounded direction (a ledger, numbers as the hero, one family, codes not symbols), the review against generic defaults (the cream-and-serif, dark-with-acid-accent and card-kit looks were considered and rejected as unrelated to the subject), and the copy rules for states and buttons. `dataviz`: the validated series hues, the mark specs, the single-axis and legend rules, and the palette validator run. Context7 confirmed the MUI 9 `createTheme` with `cssVariables`, the MUI X 9 server-side DataGrid props, TanStack Query 5's `placeholderData: keepPreviousData`, React Router 8's package layout and MSW 3's `msw/http` and `msw/node` entry points.

## 8. Text wireframes

Login:

```
┌────────────────────────────────────────────────────────────┐
│                                                            │
│              ACME Salary                                   │
│              Sign in to manage compensation                │
│              Email     [                          ]        │
│              Password  [                          ]        │
│              [ Sign in ]                                   │
│              (error line under the button)                 │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

Dashboard:

```
┌ nav ─────┐┌─────────────────────────────────────────────────────────────────────┐
│ Dashboard││ Dashboard                                 hr@acme.example  Sign out │
│ Employees││ [Country ▾] [Department ▾] [Currency USD ▾] [ ] Include exited      │
│ Imports  ││ October 2026 rates                                                  │
│          ││ ┌ Headcount ┐ ┌ Total cost   ┐ ┌ Mean gross ┐ ┌ Median gross ┐      │
│          ││ │ 9,214     │ │ USD 1.02B    │ │ USD 110,400│ │ USD 96,250   │      │
│          ││ │ 6 countr. │ │ 12 departm.  │ │            │ │              │      │
│          ││ └───────────┘ └──────────────┘ └────────────┘ └──────────────┘      │
│          ││ ┌ Where does payroll go, by country?  ⋮┐ ┌ Which departments cost most? ⋮┐│
│          ││ │ IN ▇▇▇▇▇▇▇▇▇ 41%   US ▇▇▇▇▇ 27% ...  │ │ Engineering ▇▇▇▇▇▇▇▇ USD 310M  ││
│          ││ └──────────────────────────────────────┘ │ Sales       ▇▇▇▇ USD 140M      ││
│          ││ ┌ How are salaries distributed?       ⋮┐ └────────────────────────────────┘│
│          ││ │ ▁▃▅▇▇▅▃▂▁▁▁▁   p10 ┊  p50 ┊  p90 ┊    │ ┌ What does each level pay?   ⋮┐ │
│          ││ └──────────────────────────────────────┘ │ L1 ├─•─┤  L2 ├──•──┤ ...        │ │
│          ││ ┌ Is there a gender pay gap?          ⋮┐ └────────────────────────────────┘ │
│          ││ │ IN ▇▇ ▇▇ 3.1%  US ▇▇ ▇▇ 1.8% ... Overall ▇▇ ▇▇ 2.4%   ■ female ■ male  │ │
└──────────┘└─────────────────────────────────────────────────────────────────────┘
```

Directory:

```
┌ nav ─────┐┌─────────────────────────────────────────────────────────────────────┐
│          ││ Employees                      [Export ▾] [+ Add employee]           │
│          ││ [Search name, code or email        ] [Country ▾] [Department ▾]      │
│          ││ [Designation ▾] [Level ▾] [Status ▾] [Gross USD min] [max] [Joined..]│
│          ││ ┌──────────┬───────────────┬──────────┬────┬───┬────────┬─────────┬───────────┬──────────┐
│          ││ │ Code     │ Name          │ Departm. │ Ctry│ L │ Status │ Gross (local)  │ Gross (USD)│ Joined │
│          ││ │ ACME-000017│ Asha Rao    │ Engineer.│ IN │ 3 │ active │ INR 1,450,000  │ USD 17,400 │ 3 Mar 2021 │
│          ││ │ ACME-000018│ Ben Carter  │ Sales    │ US │ 2 │ exited │ USD 98,000     │ USD 98,000 │ 9 Jun 2019 │
│          ││ │ ...   (click a row to open the employee)                                          │
│          ││ └──────────────────────────────────────────────────────────────────────────────────┘
│          ││                          Rows per page [25 ▾]   1–25 of 10,000   ‹ ›  [Columns]   │
└──────────┘└─────────────────────────────────────────────────────────────────────┘
```

New employee:

```
┌ nav ─────┐┌─────────────────────────────────────────────────────────────────────┐
│          ││ New employee                                                        │
│          ││ Identity                                                            │
│          ││ Full name [            ] Email [              ] Gender [ ▾ ]         │
│          ││ Country [ India ▾ ] Department [ ▾ ] Designation [        ] Level [3]│
│          ││ Joining date [2026-10-01]   Employee code (assigned on save)         │
│          ││ First compensation record                                           │
│          ││ Effective from [defaults to joining date]  Bonus (annual) [0]        │
│          ││ Earnings      BASE [1,450,000] HRA [580,000] ALLOWANCES [362,500]    │
│          ││ Deductions    TAX [478,500]                                          │
│          ││ Employer cost EMPLOYER_CONTRIBUTION [174,000]                        │
│          ││ Preview  gross INR 2,392,500 · net INR 1,914,000 · cost INR 2,566,500│
│          ││ Note [                      ]        [Cancel] [Save employee]        │
└──────────┘└─────────────────────────────────────────────────────────────────────┘
```

Employee detail:

```
┌ nav ─────┐┌─────────────────────────────────────────────────────────────────────┐
│          ││ ‹ Employees                                                         │
│          ││ Asha Rao  ACME-000017  [active]     [Edit] [Add revision] [Mark exited]│
│          ││ Department     Designation      Level  Country      Joined          │
│          ││ Engineering    Senior Engineer  3      India (INR)  3 Mar 2021      │
│          ││ ┌ Current record                  Version 3, effective 1 Apr 2026 ┐ │
│          ││ │ Gross per year        Net per year       Total cost per year     │ │
│          ││ │ INR 2,392,500         INR 1,914,000      INR 2,566,500           │ │
│          ││ │ USD 28,710            USD 22,968         USD 30,798              │ │
│          ││ │ INR 199,375 a month                                              │ │
│          ││ │ Component             Kind       Annual (INR)   Monthly (INR)    │ │
│          ││ │ Base salary           Earning    1,450,000.00     120,833.33     │ │
│          ││ │ House rent allowance  Earning      580,000.00      48,333.33     │ │
│          ││ │ October 2026 rate: 1 INR = 0.012 USD                             │ │
│          ││ └──────────────────────────────────────────────────────────────────┘ │
│          ││ [ History ]  [ Audit ]                                              │
│          ││ v4  from 1 Apr 2027             [scheduled]  INR 2,560,000  [Cancel]│
│          ││ v3  1 Apr 2026 onwards          [current]    INR 2,392,500  annual raise│
│          ││ v2  1 Apr 2025 to 31 Mar 2026   [ended]      INR 2,200,000          │
│          ││ (a cancelled row is greyed, its gross struck through, "Cancelled <date> by <who>")│
└──────────┘└─────────────────────────────────────────────────────────────────────┘
```

Imports:

```
┌ nav ─────┐┌─────────────────────────────────────────────────────────────────────┐
│          ││ Imports                                     [Download template ▾]   │
│          ││ ┌ - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - ┐ │
│          ││ │   Drop a .xlsx or .csv here, or choose a file. Up to 10,000 rows. │ │
│          ││ └ - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - ┘ │
│          ││ File                 Uploaded          Status     Rows  Valid Warn Err │
│          ││ october-raises.xlsx  7 Oct 2026 09:12  [review]   50    44    3    3   │
│          ││ new-joiners.csv      6 Oct 2026 17:40  [approved] 12    12    0    0   │
│          ││ bad-headers.xlsx     6 Oct 2026 17:31  [discarded] ...                 │
│          ││ (warnings under a row: Ignored unknown column: Remarks)               │
│          ││ (empty: No imports yet. Download the template, fill it in and drop it here.) │
└──────────┘└─────────────────────────────────────────────────────────────────────┘
```

Import review:

```
┌ nav ─────┐┌─────────────────────────────────────────────────────────────────────┐
│          ││ ‹ Imports   october-raises.xlsx  [review]      [Discard] [Approve]  │
│          ││ Total 50 · Valid 44 · Warning 3 · Error 3 · Skipped 0 · No-op 2     │
│          ││ Status [All ▾]  [Search code or name     ]      (Approve tooltip:   │
│          ││                                                  3 rows have errors) │
│          ││ ┌───┬─────────┬────────┬────────────┬──────────┬──────┬────────┬────┐│
│          ││ │ # │ Status  │ Action │ EmployeeID │ Name     │ BASE │ HRA    │ …  ││
│          ││ │ 12│ [error] │ revise │ ACME-000012│ R. Iyer  │-5,000│ 40,000 │skip││
│          ││ │   │ BASE must be a non-negative number, got -5000 (cell tinted)   ││
│          ││ │ 13│ [warning]│ revise│ ACME-000013│ M. Khan  │ ...  gross below minimum ││
│          ││ │ 14│ [valid] │ noop   │ ACME-000014│ ...      │ No changes, row will be skipped ││
│          ││ └───┴─────────┴────────┴────────────┴──────────┴──────┴────────┴────┘│
│          ││                                   Rows per page [50 ▾]  1–50 of 50   │
└──────────┘└─────────────────────────────────────────────────────────────────────┘
```

## 9. Testing

Backend layout: `backend/tests/conftest.py`, `tests/factories.py`, then `tests/<app>/test_<unit>.py` mirroring `apps/`. Settings `acme_salary.settings.test` with in-memory SQLite, `PASSWORD_HASHERS = [MD5PasswordHasher]` for speed, the login throttle kept so the 429 test is real.

Fixtures (`conftest.py`): `lookups` (calls `ensure_lookups`), `rates` (calls `ensure_rates`, sixteen rows), `today` (`freeze_time("2026-10-07")`, applied to every test through `autouse`), `hr_user` (`UserFactory`), `api` (`APIClient` with a bearer token for `hr_user`), `anon` (bare `APIClient`), `clear_throttle_cache` (autouse, `cache.clear()`).

Factories (`factory_boy`): `UserFactory`, `EmployeeFactory` (sequence codes `ACME-9NNNNN` so they never collide with seed codes, `country` and `department` taken from the lookups, `joining_date = 2020-01-01`), `CompensationRecordFactory` (`version` from a per-employee sequence, `effective_from = joining_date`, `currency_code` from the country, totals computed by the service in a `post_generation` hook from a `lines` mapping, default `{"BASE": 100000}` plus the country's required lines at zero), `ExchangeRateFactory`, `ImportBatchFactory`, `ImportRowFactory`, `AuditLogFactory`. Factories create the minimum rows and never call the 10k seed.

Service tests per app (SPEC section 12 table, one file per unit): `tests/compensation/test_totals.py`, `test_services.py` (next-day revision, scheduled revision, cancel and re-chain, exit closing, the one-open-record invariant through the constraint, version assignment, the 409 and 400 cases), `test_bulk_apply.py` (equality with the single path, chunking at 1,001 entries), `test_validators.py` (every section 7 rule with one passing and one failing case, asserting field, severity and the full message); `tests/core/test_fx.py` (rate by date, the earliest-rate fallback, routing through USD, the inverse-leg fallback, `convert` precision, `case_expression` SQL against a small directory) and `test_set_exchange_rate.py`; `tests/employees/test_services.py` and `test_queries.py` (`pick_shown` against the subquery, the annotation on a fixture with current, scheduled, exited and cancelled rows, `gross_bound`); `tests/imports/test_parser.py` (header aliases, `1,200`, `12,00,000`, `1.200.000,50`, Excel dates, the 10,001st row), `test_staging.py` (the decision table row by row, counts unchanged on live tables), `test_review.py` (skip, unskip, discard, 409s), `test_applier.py` (approve happy path over a fixture that includes a promotion row changing identity and amounts and an exit-with-raise row, with the audit count `2 x created + updated + revised + (revised rows that also changed identity or set last_date) + 1`, the simulated failure through a monkeypatched `bulk_create` raising mid-way, re-validation after a UI revision); `tests/audit/test_snapshots.py` and `test_record.py`; `tests/exports/test_writers.py` (escaping in CSV and XLSX, the BOM, row counts); `tests/seed/test_seed.py` (slow).

API tests use `APIClient` and pin query counts on list, detail and insight endpoints with `django_assert_num_queries`. Every error case asserts the message and the field.

The insight fixture (`tests/insights/fixture.py`, `build_fixture() -> Fixture`) is thirty employees built with the factories against rates set in the fixture itself (INR to USD 0.0125, EUR to USD 1.25, GBP to USD 1.25, USD to EUR 0.8), reporting date 2026-10-07:

| Group | Rows | Gross (local) | Lines | Department, gender, level |
| --- | --- | --- | --- | --- |
| US active U1 to U10 | 10 | 100k, 110k, ... 190k USD | BASE = gross, TAX 20%, EMPLOYER_CONTRIBUTION 10% | U1 to U5 Engineering, U6 to U10 Sales; U1 to U6 male, U7 to U10 female; levels 1,1,2,2,3,3,4,4,5,6 |
| US exited X1 | 1 | 120k USD, `last_date` 2026-06-30 | as above | Engineering, male, level 3 |
| IN active I1 to I12 | 12 | 800k + 200k x i INR, i = 0..11 | BASE 60%, HRA 25%, ALLOWANCES 15%, TAX 10%, EMPLOYER_CONTRIBUTION 12% | I1 to I6 Engineering, I7 to I12 Support; even i male, odd i female; levels cycle 1..6 |
| IN exited X2 | 1 | 500k INR, `last_date` 2020-12-31 | as IN | Support, female, level 1 |
| DE active D1 to D4 | 4 | 60k, 70k, 80k, 90k EUR | BASE = gross, SOCIAL_INSURANCE 20%, EMPLOYER_CONTRIBUTION 20% | Engineering, two female two male, levels 2,3,4,5 |
| DE future joiner D5 | 1 | 100k EUR, `joining_date` 2026-12-01 | as DE | Engineering, male, level 3 |
| GB active G1 | 1 | 50k GBP | BASE = gross, NATIONAL_INSURANCE 10%, EMPLOYER_CONTRIBUTION 14% | Finance, female, level 2 |

Plus: U1 has a scheduled revision effective 2027-01-01 at 130k; I3 has a cancelled scheduled revision at 5M INR; the Legal department has nobody; the record dates are all 2024-01-01 unless stated. Hand-computed expectations written into the tests, USD, no filters, today:

- `summary`: headcount 27 (10 + 12 + 4 + 1), total cost 2,435,450.00 (US 1,595,000 + IN 25,536,000 INR x 0.0125 = 319,200 + DE 360,000 EUR x 1.25 = 450,000 + GB 57,000 GBP x 1.25 = 71,250), mean gross 80,462.96 (2,172,500 / 27), median gross 75,000.00 (the 14th of 27 sorted converted values: twelve IN values 10,000 to 37,500, then 62,500, then 75,000), countries 4, departments 4.
- `summary` with `include_exited=true`: headcount 29, total cost adds X1 132,000 and X2 560,000 INR x 0.0125 = 7,000.
- `summary` with `on=2027-01-01`: U1 counts at 130,000 (its scheduled revision is current) and D5 is active (joined 2026-12-01), so headcount 28, total cost 2,618,450.00 (2,435,450 + 33,000 + 150,000), mean gross 83,125.00 (2,327,500 / 28). X1 and X2 stay excluded.
- `by-country`: US headcount 10, total cost 1,595,000.00, median 145,000.00, share 65.5; IN 12, 319,200.00, 23,750.00 (median of 12 values, the mean of 1.8M and 2.0M INR), 13.1; DE 4, 450,000.00, median `null` (under five), 18.5; GB 1, 71,250.00, `null`, 2.9.
- `by-department`: Engineering headcount 15 (U1 to U5, I1 to I6, D1 to D4), total cost 1,219,200.00 (660,000 + 109,200 + 450,000), mean 71,500.00 (1,072,500 / 15), median 87,500.00 (the 8th of 15); Legal headcount 0 with nulls; Finance headcount 1 with count and total only.
- `distribution` with `country=US`: ten values 100,000 to 190,000; p1 100,900, p99 189,100 (inclusive method), band width 7,350, counts `[1,1,1,1,0,1,1,0,1,1,1,1]`, markers p10 109,000, p50 145,000, p90 181,000.
- `gender-gap` row IN: female median 25,000.00 (2.0M INR), male median 22,500.00 (1.8M INR), `gap_pct` -11.1; row US: female headcount 4 so `gap_pct null`, reason `group too small`; overall row computed over all 27.
- `by-level` with `country=US`: level 1 headcount 2 so all five figures `null`. Unfiltered, level 3 has exactly five people (U5 140,000, U6 150,000, I3 15,000, I9 30,000, D2 87,500; X1 and D5 are excluded), which tests the boundary: min 15,000.00, p25 30,000.00, median 87,500.00, p75 140,000.00, max 150,000.00 (inclusive method over five values).

One test per filter per insight, plus the API test with the pinned query count and the 404 for an unknown name.

Frontend: Vitest with `environment: 'jsdom'`, `src/test/setup.ts` starts `setupServer(...handlers)` from `msw/node` with `onUnhandledFrame: 'error'` (MSW 3 renamed `onUnhandledRequest`), resets handlers after each test; handlers in `src/test/handlers.ts` use `http` and `HttpResponse` from `msw/http` (SPEC section 1); fixtures in `src/test/fixtures/` carry four employees (IN active, US active, GB exited, DE with a scheduled revision), one batch with five rows (valid, warning, error, skipped, no-op), and insight payloads in the shapes of section 1.6 with small numbers; `src/test/render.tsx` wraps a component in `QueryClientProvider` (retries off) and a `MemoryRouter`. Tests query by role and label. Unit tests: `serverModel.test.ts` (zero-based page mapping, ordering prefix, URL round trip), `money.test.ts`, `dates.test.ts`, `client.test.ts` (one refresh for two concurrent 401s, redirect after the second), `useUrlFilters.test.ts` (`include_exited`, the local-currency rule). Component tests: `Login.test.tsx` (redirect to `next`), `Employees.test.tsx` (renders fixture rows, a filter change calls the API with the right params, error state), `EmployeeDetail.test.tsx` (history with the cancelled row greyed, cancel on the scheduled row only), `EmployeeForm.test.tsx` (zod message, server field error mapped), `ImportReview.test.tsx` (status filter, approve disabled with the reason), `Dashboard.test.tsx` (each card shows the fixture numbers, a filter change refetches, the include-exited box changes headcount).

## 10. Deployment

Dockerfile, two stages:

```
FROM node:26-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend/ ./
RUN npm run build                                  # vite base "/", output dist/

FROM python:3.14-slim
RUN pip install --no-cache-dir uv                  # or COPY --from=ghcr.io/astral-sh/uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev
COPY backend/ ./
COPY --from=web /web/dist /app/spa
RUN .venv/bin/python -m whitenoise.compress /app/spa   # gzip and brotli beside each asset
COPY entrypoint.sh /app/entrypoint.sh
ENV PATH=/app/.venv/bin:$PATH DJANGO_SETTINGS_MODULE=acme_salary.settings.prod SPA_DIR=/app/spa
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
```

`entrypoint.sh`:

```
set -euo pipefail
python manage.py migrate --noinput
python manage.py flushexpiredtokens
python manage.py seed_data --employees 10000 --seed 42 --if-empty
exec gunicorn acme_salary.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 8 --timeout 120
```

Step 1 confirms the image's SQLite with `docker run --rm <image> python -c "import sqlite3; print(sqlite3.sqlite_version)"` against Django 6.1's 3.37 minimum and records it in the step's DECISIONS entry.

Environment variables (`.env.example` is committed with placeholders; `.env` never is):

| Variable | Dev default | Production |
| --- | --- | --- |
| `SECRET_KEY` | a dev-only value in `dev.py` | `fly secrets` |
| `DEBUG` | `1` | `0` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | `acme.nutanprabhat.dev` only, so `acme-salary.fly.dev` answers 400 and the site has one name |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | `https://acme.nutanprabhat.dev` |
| `CSRF_TRUSTED_ORIGINS` | same | `https://acme.nutanprabhat.dev` |
| `DATABASE_PATH` | `backend/db.sqlite3` | `/data/db.sqlite3` |
| `SEED_ADMIN_PASSWORD` | `change-me` | `fly secrets`, required |
| `SPA_DIR` | unset (Vite dev server) | `/app/spa` |
| `PORT` | `8000` | `8000` from `fly.toml` |

Volume: `fly.toml` mounts volume `data` at `/data`; the database, its WAL and shm files live there. `docker-compose.yml` maps port 8000 and a named volume `acme-data:/data`, with the same environment names read from `.env`.

Fly setup, done by the owner on 7 October before step 1 (D29, D30): the volume `data` in `sin`, the secrets above, `fly certs add acme.nutanprabhat.dev` (issued and verified on IPv4 and IPv6), and a Cloudflare CNAME `acme` to `acme-salary.fly.dev` with the proxy off. The step 1 deploy could not place a 1 GB machine on that volume's host, so a second empty volume named `data` was created in `sin`, the machine runs on it, and the first, never-attached volume was destroyed, leaving one machine and one volume (D31). `fly deploy --remote-only` builds on Fly's builder, and the ask rule prompts for it at the close of every step that adds a page. `.dev` is HSTS-preloaded, so the site is reachable only over the issued certificate. The health check in `fly.toml` hits `/healthz` every 30 s and sends `Host: acme.nutanprabhat.dev` through `[http_service.checks.headers]`, because Fly's checker otherwise sends the machine's internal address as `Host` and `ALLOWED_HOSTS` answers 400 (D29). Fly caps an HTTP service check grace at 60 s and `fly.toml` says `grace_period = '60s'` (D31). A failed check does not restart the machine, it only stops routing and makes `fly deploy` wait, so the seeded first boot, once per volume, runs with `fly deploy --remote-only --wait-timeout 10m` and its measured boot goes into `docs/PERFORMANCE.md`; later boots skip the seed and were healthy 6 s after init.

CI (`.github/workflows/ci.yml`): `backend` job (`setup-python` 3.14, `astral-sh/setup-uv`, `uv sync`, `ruff format --check`, `ruff check`, `pytest -q`), `frontend` job (`setup-node` with `node-version-file: frontend/.nvmrc` and `cache: npm`, `npm ci`, `npm run lint`, `npm test -- --run`, `npm run build`), `docker` job after both (`docker build .`). `npm install` never runs in CI.

## Questions for the owner

Answered on 7 October 2026 and recorded in `docs/DECISIONS.md` D24 to D30. The sections above already reflect the answers.

1. Approve after the data changed: the default, those rows re-marked `error`, the batch stays in `review`, 409 with the rows (D24).
2. By-level under five people: the general rule, SPEC section 9 corrected (D25).
3. Audit action for an import row that sets `last_date`: the default, one `exit` entry (D26).
4. Cancelling a future joiner's only record: the default, 409 (D26).
5. JSON export shape and UTC file stamps: the default (D27).
6. Money as strings: the default (D27).
7. Warnings on create and revise: the default (D27).
8. DNS: a CNAME only, proxy off, SPEC section 14 corrected (D29).
9. Rate month label: the default (D28).
10. Percentages with one decimal: the default (D27).
11. Upload content types: the default (D27).
12. Light theme only (D28).
13. Approve failure response: 409 with the same body, not 500 (D24).
14. Sample data: the default (D28).
