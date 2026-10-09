Owner decision: approved. Steps 1 to 7 on 7 October, steps 8 to 10 on 8 October with the changes recorded in D62, D64 and D72.

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

- `DATABASES["default"]`: sqlite3 at `DATABASE_PATH` (env, default `backend/db.sqlite3`; `prod.py` requires it as an absolute path, so a missing or relative value cannot put the database on the ephemeral root filesystem, D73), `OPTIONS = {"transaction_mode": "IMMEDIATE", "init_command": "PRAGMA journal_mode=WAL;", "timeout": 20}` (SPEC section 13). `test.py` uses `:memory:`, and its `SECRET_KEY` is among the placeholders `prod.py` refuses (D73).
- `REST_FRAMEWORK`: `JWTAuthentication` only, `IsAuthenticated` by default, `JSONRenderer` only (no browsable API), `DEFAULT_PAGINATION_CLASS = "apps.core.pagination.StandardPagination"`, `DEFAULT_FILTER_BACKENDS = [DjangoFilterBackend, SearchFilter]`, `DEFAULT_THROTTLE_RATES = {"login": "5/min", "refresh": "30/min", "reset": "5/hour"}`, `NUM_PROXIES = env_int("NUM_PROXIES", 1)`, 1 behind Fly's proxy and 0 in compose (D73), `EXCEPTION_HANDLER = "apps.core.exceptions.handler"`, `COERCE_DECIMAL_TO_STRING = True` so money leaves the API as a two-decimal string.
- `SIMPLE_JWT`: access 30 minutes, refresh 12 hours, `ROTATE_REFRESH_TOKENS = True`, `BLACKLIST_AFTER_ROTATION = True`.
- `CACHES`: `LocMemCache` (one gunicorn worker, so the throttle counter is shared by all threads).
- `INSTALLED_APPS`: `django.contrib.auth` and `contenttypes` (needed by the user model and the blacklist app), `rest_framework`, `rest_framework_simplejwt.token_blacklist`, `django_filters`, `corsheaders`, the eight apps under `apps/` and `seed`. No admin, no sessions, no messages, no staticfiles app.
- `MIDDLEWARE`: `SecurityMiddleware`, Django 6.1's `ContentSecurityPolicyMiddleware` (D38), `apps.core.middleware.NoStoreApiMiddleware` (`Cache-Control: no-store` on `/api/` responses, D41), `XFrameOptionsMiddleware` above WhiteNoise so static files carry the header too (D73), `WhiteNoiseMiddleware`, `CorsMiddleware`, `CommonMiddleware`. JWT needs neither session nor Django's auth middleware.
- `prod.py`: `DEBUG = False`, `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` from the environment, `WHITENOISE_ROOT = SPA_DIR` (env, default `/app/spa`), `WHITENOISE_MAX_AGE = 60`, `WHITENOISE_IMMUTABLE_FILE_TEST` returning true for URLs under `/assets/`. HSTS headers are left to the `.dev` preload list.
- `acme_salary/urls.py`: `path("api/v1/", include(...))` for each app, `path("healthz", core.views.healthz)`, then `re_path(r"^(?!api/|assets/|healthz).*$", spa.index)` which returns `index.html` from `SPA_DIR` and 404 when the directory is absent (dev mode, where Vite serves the SPA).

`apps/core` holds what every app shares:

| Module | Contents |
| --- | --- |
| `pagination.py` | `StandardPagination(PageNumberPagination)`: `page_size = 25`, `page_size_query_param = "page_size"`, `max_page_size = 100` |
| `exceptions.py` | `DomainError` base. `Invalid(errors: dict[str, list[str]])` maps to `400 {field: [message]}`. `Conflict(detail, **extra)` maps to `409 {"detail": ..., ...extra}`. `PayloadTooLarge` is a DRF `APIException` with status 413. `ApplyFailed` is an `APIException` with status 409 carrying `detail` and `error_summary` (D24). `clip(value, limit=ECHO_LIMIT)` cuts any value a message repeats to 64 characters ending in `…` (D56), so `msg()` and the `on`, `currency` and country 400s of `dates.py` and `fx.py` cut alike. `handler(exc, context)` wraps DRF's default handler and maps these four; everything else keeps DRF's shape |
| `money.py` | `q2(x)`, `to_str(x)` (two decimals), `render(payload)` walks dicts and lists turning `Decimal` into strings and dates into ISO text. Insight and exchange-rate responses pass through `render` so no `Decimal` reaches DRF's encoder, which would turn it into a float |
| `dates.py` | `today_utc()`, `parse_on(value)` (ISO date or `Invalid({"on": [...]})`), `month_label(d)` ("October 2026") |
| `filters.py` | `CharInFilter`, `NumberInFilter` (comma-separated `BaseInFilter` subclasses), `parse_csv(value) -> list[str]`, `parse_bool(value, *, name, default=False)` (`true`, `false`, `1`, `0`, `yes`, `no`, `on` or `off` in any case, anything else a 400 `<name> must be true or false`) |
| `fx.py` | section 4 |
| `services.py` | `set_exchange_rate`, section 4 |
| `views.py` | `healthz` (a plain Django view outside DRF, runs `User.objects.order_by().exists()` so one query proves the database answers, returns `{"status": "ok"}`; the user table exists from step 1, the lookups only from step 2), the four `/meta/` views |
| `management/commands/set_exchange_rate.py`, `timing.py` | thin wrappers: parse arguments, call the service, print |

Models in `core/models.py` follow SPEC section 5 "Lookups". `ExchangeRate.Meta.constraints`: `UniqueConstraint(from_currency, to_currency, effective_from)`, `UniqueConstraint(fields=["from_currency", "to_currency"], condition=Q(effective_to__isnull=True), name="one_open_rate_per_pair")`, `CheckConstraint(condition=Q(effective_to__isnull=True) | Q(effective_to__gt=F("effective_from")))`, `CheckConstraint(condition=Q(rate__gt=0))`, `CheckConstraint(condition=~Q(from_currency=F("to_currency")))`. Django 6.1 spells these with `condition=`.

The lookup rows (six countries, twelve departments, ten components) are data, not a migration: `seed/lookups.py` has `ensure_lookups()` (idempotent `update_or_create` by code from `seed/profiles.py`) and `ensure_rates()` (the sixteen rate rows through `set_exchange_rate`, September before October). `seed_data` calls both; the test fixture `lookups` calls the first. Migrations stay schema-only, and `reset_demo` can truncate and rebuild everything the determinism scope names.

Meta endpoints (SPEC section 8): `/meta/countries/` returns `[{code, name, currency_code, min_gross_annual}]`; `/meta/departments/` returns `[{id, code, name}]`; `/meta/components/?country=` returns the global components plus that country's, ordered by `sort_order`, as `[{id, code, name, kind, country, sort_order}]`, 404 for an unknown country, all components when omitted; `/meta/exchange-rates/?on=` returns `{"on", "rates": [{from_currency, to_currency, rate, effective_from}], "month_labels": {"USD": "October 2026 rates", "EUR": "October 2026 rates"}}`.

### 1.1 accounts

- Model: `User` as SPEC section 5 "Users", with a `UserManager` whose `create_user(email, password)` lowercases the email. `REQUIRED_FIELDS = []`.
- Views: `LoginView(TokenObtainPairView)` with `throttle_classes = [ClientAddressThrottle]` (a `ScopedRateThrottle` keyed on the client address, an IPv4-mapped address unmapped first and an IPv6 client reduced to its /64, D41, D73) and `throttle_scope = "login"`; `RefreshView(TokenRefreshView)` with the same throttle on scope `refresh` at 30 a minute and `parser_classes = [JSONParser]` (D73); `LogoutView(TokenBlacklistView)` behind `IsAuthenticated`, body `{refresh}`; `MeView(APIView)` returning `{id, email}`. SimpleJWT's default serializer keys on `USERNAME_FIELD`, so the login body is `{email, password}` with no custom serializer.
- Session rules (SPEC F8, D21): `SessionRefreshSerializer(TokenRefreshSerializer)`, wired through `SIMPLE_JWT["TOKEN_REFRESH_SERIALIZER"]`, calls one function in `accounts/services.py`, `refresh_session(raw) -> (access, refresh)`, which decodes the token, checks its user is active and calls `rotate`, and on any `TokenError`, a token that fails to decode or one another request rotated meanwhile, calls `revoke_on_reuse` before re-raising (D73). `rotate(refresh) -> (access, refresh)` runs inside one `transaction.atomic()`, which SQLite opens for writing at once, re-checks the token's row for a blacklist entry and raises `TokenError` if it has one, then blacklists the presented token and issues the pair with the original `exp` kept, so a session ends 12 hours after login, and caps the access token's `exp` at the refresh token's. `revoke_on_reuse(raw) -> int` matches the presented string to an `OutstandingToken` that has a `BlacklistedToken` row, takes the user from that row (never from an unverified payload), blacklists every outstanding token of that user, logs a warning and returns the count; the serializer then answers 401. `revoke_sessions(user) -> int` is the same revoke-all, also exposed as `python manage.py revoke_sessions <email>`.
- Revoke claim (D76): `SIMPLE_JWT["CHECK_REVOKE_TOKEN"] = True`, so `RefreshToken.for_user` writes SimpleJWT's `hash_password` claim, a hash of the user's password, `rotate` keeps it on the new refresh token and copies it to the access token it mints, and `JWTAuthentication` refuses a token whose claim no longer matches. A password change therefore ends every session issued before it, and `revoke_sessions` stays the operator's second step.
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

`employees/filters.py` has `DirectoryFilterSet(FilterSet)` with the exact parameter names of SPEC F4: `country`, `department` (both `CharInFilter` on `country__code`, `department__code`), `designation` (a `CharInFilter` with a `method` that matches each value case-insensitively, `designation__iexact`), `level` (`ChoiceInFilter`, values 1 to 6 so a stray value is a 400), `status` (`ChoiceFilter` on the annotation, `active` when not given and `any` for everyone, so the directory and its export open on the employees on staff, D64), `gross_min` and `gross_max` (`NumberFilter(method=...)` calling `gross_bound`), `joined_after` and `joined_before` (`DateFilter` on `joining_date` with `gte` and `lte`), and `ordering = OrderingFilter(fields=(("full_name", "full_name"), ("id", "employee_code"), ("department__name", "department"), ("country__name", "country"), ("designation", "designation"), ("level", "level"), ("gross", "gross"), ("joining_date", "joining_date")))`. Default order `id`, the code ascending, which the grid marks by default, so a request without `ordering`, the directory's or its export's, returns the order the grid shows (D63). Every ordering ends with `id`, so pages are stable. `search` is `EmployeeSearchFilter`, a `core.filters.BoundedSearchFilter` (terms capped at ten) where each word matches `full_name` or `email` in part, `legacy_code` in any case, or an ACME code that `queries.parse_employee_code` reads as an id, so `ACME-0017` and `acme-17` both find ACME-17; words combine with AND (D48). A FilterSet maps parameters to lookups and holds no rules; the tolerance lives in `queries.gross_bound`.

`employees/services.py`:

| Function | Contract and exceptions |
| --- | --- |
| `parse_employee_code(text) -> int \| None` | In `employees/queries.py`: the id an ACME code names, read as a number (`ACME-0017` gives 17), for search. The employee code itself is `Employee.employee_code`, the property `ACME-<id>`; the database assigns the id and nothing stores the code (D48) |
| `create_employee(identity: dict, record: RecordInput, *, actor) -> Employee` | One transaction, with `validators.validate_identity` and `validators.validate_record` run inside it so SQLite's write lock covers the check (D44), `Invalid` on any error. `validators.refuse_codes` answers 400 when the body carries `employee_code` or `legacy_code` (D48); the database numbers the employee. Saves the employee with `created_at = updated_at = now`. Calls `compensation.services.add_first_record`. Writes audit `create` on the employee (`before = None`). Returns the employee; the view serialises it with the validators' warnings in a `warnings` list |
| `update_identity(employee, changes: dict, *, actor) -> Employee` | `employee_code` or `legacy_code` in `changes` raises through `validators.refuse_codes`, whatever the value (D48), and a changed `country_code` raises `Invalid({"country_code": ["country_code cannot be changed"]})`. Inside one transaction: re-reads the employee, validates (a `joining_date` past the first record is a 400, D45), applies, sets `updated_at`, audit `update` with before and after snapshots. When the applied changes leave the snapshot as it was, as with an empty body, nothing is saved and no entry is written |
| `exit_employee(employee, last_date: date, *, actor, today: date | None = None) -> Employee` | Inside one transaction, after re-reading the employee (D44), checks in this order: already exited, `Conflict("employee already exited on <date>")`; `last_date < joining_date`, `Invalid({"last_date": ["last_date precedes joining_date"]})`; any live record with `effective_from > today` and `effective_from > last_date`, other than a first record that has never been current, `Conflict("scheduled revision on <date> must be cancelled before exit")`; the open record's `effective_from > last_date`, `Invalid({"last_date": ["last_date precedes the current record (effective <date>)"]})`. Then: `last_date` set, `compensation.services.close_open_record(employee, at=last_date + 1 day)`, `updated_at`, audit `exit` on the employee whose `after` snapshot shows the closed record. A future `last_date` passes the same checks and is a scheduled exit. When the only live record starts after `last_date` and has never been current, `validate_exit` returns it and the exit cancels it instead of closing it: the `exit` entry's `after` shows no record, then `compensation.services.cancel_unstarted(record, employee)` writes `cancel` (D50) |

Serializers (`compensation/serializers.py` for the record input, `employees/serializers.py` for the rest), shape and types only:

- Input: `LineInputSerializer {component: code (at most 64 characters), annual_amount: Decimal}`, `RecordInputSerializer {effective_from?: date, bonus_annual?: Decimal (missing is zero), note: str = "" (at most 1,000 characters), lines: [LineInput] (at most 20)}`, which refuses a component listed twice (`BASE appears twice in lines`, D46), `EmployeeCreateSerializer` (the body in SPEC section 8 for `POST /employees/`, a `RecordInputSerializer` plus the identity fields, with `department`, `country_code` and `gender` at most 64 characters, D51), `EmployeeIdentitySerializer` (identity fields, all optional, plus `employee_code`, `legacy_code` and `country_code` as optional fields so the service can reject them with 400 rather than the serializer silently dropping them; the create body reads the two codes the same way), `ExitSerializer {last_date}`.
- Output: `EmployeeListSerializer` (id, employee_code (`ACME-<id>`), legacy_code, full_name, email, department `{code, name}`, designation, level, country `{code, name, currency_code}`, status, joining_date, last_date, `shown: {record_id, version, effective_from, effective_to, is_current, label, gross_local, currency_code, gross_reporting, reporting_currency}`). `EmployeeDetailSerializer` (the identity fields with `employee_code` and `legacy_code`, `status`, `shown_label`, `current_record` as a full `CompensationRecordSerializer`, `created_at`, `updated_at`). `CompensationRecordSerializer` (id, employee id, version, effective_from, effective_to, is_current, is_scheduled, cancelled_at, cancelled_by email, currency_code, bonus_annual, gross_annual, net_annual, total_cost_annual, source, note, created_at, created_by email, `lines: [{component: code, annual_amount}]` with names and kinds read from `/meta/components/` on the client (D34), `converted: {currency, rate, rate_effective_from, bonus_annual, gross_annual, net_annual, total_cost_annual}`). `AuditEntrySerializer` (id, timestamp, actor email or null, action, entity_type, entity_id, before, after, import_batch). Converted figures come from `rates.convert` with the `RateTable` in the serializer context; the serializer calls `core/fx.py`, it computes nothing itself. Totals are read-only everywhere. The record and employee shapes follow the audit snapshots, datetimes included (`+00:00`, not DRF's `Z`), and `tests/audit/test_snapshots.py` holds them equal (D34).

Views (`employees/views.py`): `EmployeeListCreateView(DirectoryMixin, ListCreateAPIView)`. `DirectoryMixin`, which the directory export shares (1.7), holds the filter backends, and its `get_queryset` parses `on` and `currency` (`fx.resolve_reporting_currency` with the `country` filter values), loads one `RateTable` for the request, and returns `directory_queryset`; `filterset_class = DirectoryFilterSet`, `search_fields` as above. `designation` takes at most 20 titles, each one more OR, since SQLite answers an expression deeper than 1,000 with a 500 (`designation accepts at most 20 titles`, D61). `POST` calls `create_employee` and returns 201 with the detail shape plus `warnings`. `EmployeeDetailView(RetrieveUpdateAPIView)` for GET and PATCH, no PUT. `EmployeeExitView(GenericAPIView)` for POST. Writes parse `on` and `currency` before the service runs, so a bad parameter is a 400 with nothing written, and answer with the detail shape read back through `detail_queryset`. PATCH fetches its target without the records prefetch, since the service re-reads it. `EmployeeAuditView(ListAPIView)` over `AuditLog.objects.filter(employee=...)`, newest first, paginated.

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
| `cancel_unstarted(record, employee, *, actor=None, at=None) -> CompensationRecord` | Exit support only (D50), called inside the exit's transaction after its `exit` entry: marks the employee's only, never-current record cancelled. Nothing precedes it, so nothing is re-chained. Audit `cancel` with the record before and after. `bulk_apply` does the same for an exit entry with one bulk update |
| `close_open_record(employee, *, at: date) -> CompensationRecord` | Sets `effective_to = at` on the open live record. Caller has checked `at > effective_from`. Not audited on its own: the caller's `exit` entry carries it |
| `bulk_apply(entries: Sequence[BulkEntry], *, actor, source, batch=None, at: datetime, ctx: ValidationContext) -> BulkResult` | The entry point the seed and the import applier share, below |

`BulkEntry(employee: Employee | None, identity: dict | None, identity_changes: dict | None, last_date: date | None, records: list[RecordInput], ref: Any)`. A create carries `identity` and one or more records (the seed passes a whole history with explicit `effective_from` values). An update carries `employee` and `identity_changes`. A revise carries `employee`, one record and optional `identity_changes`. An exit carries `employee` and `last_date` with optional `identity_changes`. `ref` is handed back in `BulkResult` so the applier can match rows.

`bulk_apply` runs inside the caller's transaction and does, in order: validate every entry with the validators against `ctx` (an error raises `BulkInvalid(ref, messages)`; the seed never trips it and the applier has pre-validated); build `Employee` objects (the database numbers them, and an import create keeps its sheet's `legacy_code`, D48) and `bulk_create(batch_size=1000)` (SQLite 3.35 and later return primary keys, so the objects are usable after the call); apply identity changes and exits to existing employees with `bulk_update`; build records with `chain_records` (each record's `effective_to` is the next one's `effective_from`, the last is open) and versions continuing from the employee's maximum, totals from `compute_totals`, closing the previous open record for revises and exits in one `bulk_update`, and marking cancelled, in a second, the only record of an employee whose exit comes before pay starts (D50); `bulk_create` the records, then the lines; build audit rows with `audit.snapshot_record` over the in-memory objects and `audit.bulk_record` them. Every batch is 1,000 objects. The single-row functions and the bulk path share `compute_totals`, the validators, `chain_records`, the version rule and the snapshot functions, and a test asserts that `revise()` and `bulk_apply()` given the same input produce the same rows apart from ids and timestamps.

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
    legacy_code: str | None                  # an import row names its employee by legacy_code
    employee_id: int | None                  # an API call names it by id (D48)
    full_name, email, department, designation, level, country_code, gender
    joining_date, last_date, effective_from: date | None
    bonus_annual: Decimal | None
    amounts: dict[str, Decimal | None]       # component code -> amount, only columns present
    columns: set[str]                        # columns the sheet has, or the fields an API call names
    present: set[str]                        # of those, the non-blank ones
    parse_messages: list[Message]            # from the parser: bad numbers, bad dates
    # set by rules
    identity_changed: bool = False
    identity_changes: dict[str, Any] = {}    # what changed, as bulk_apply writes it
    amounts_changed: bool = False
    noop: bool = False

@dataclass
class ValidationContext:        # built once per upload, per API call, per seed chunk; rules do no database access
    today: date
    countries: dict[str, Country]
    departments: dict[str, Department]
    components_by_country: dict[str, dict[str, SalaryComponent]]   # global ones merged into every country
    employees_by_id: dict[int, Employee]; employees_by_legacy: dict[str, Employee]
    email_owner: dict[str, int]                 # lowercase email -> employee id
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
| Structure and types | `check_legacy_code` (import only), `check_required_cells` (a blank required cell, after which the rules on that cell stay silent, D56), `check_text_lengths` (a cell longer than its column, D55), `check_email_format`, `check_country_exists`, `check_department_exists`, `check_level_range`, `check_gender_enum`, `check_parse_messages` (re-emits the parser's date and number messages), `check_dates_in_range` (every date on or before 2100-12-31, in all four scopes, D53), `check_base_required` (blank, or under 10, D49), `check_bonus_non_negative`, `check_amounts_non_negative`, `check_amounts_in_range` (each amount at most 9,999,999,999.99, D49), `check_decimal_places`, `check_components_applicable` | legacy_code blank or longer than 32; a required cell blank; a cell longer than its column; email malformed; Unknown country_code; Unknown department; level; gender; date unparseable; a date after 2100-12-31; comma decimal; more than two decimals; amount negative or non-numeric; BASE required; bonus_annual negative; an amount over the cap, BASE under 10; component not applicable |
| Identity references | `check_email_in_use` (an unknown legacy_code whose email is taken is this error, never a second person, D48), `check_country_unchanged` | email already belongs to; country change not supported |
| Duplicates within the file | `check_duplicate_legacy`, `check_duplicate_email` | Duplicate legacy_code in rows 41 and 388; Duplicate email in rows 12 and 90 (both rows get it) |
| Amounts changed | `check_identity_changed`, `check_amounts_changed` (set the flags; a new employee has both true) | the decision table in F1 |
| No-op | `check_noop` (info `No changes, row will be skipped on apply`, sets `row.noop`) | Row identical to the current record |
| Date rules (skipped when `row.noop`) | `check_last_date_after_joining`, `check_joining_before_first_record` (D45), `check_last_date_vs_open_record`, `check_last_date_cleared`, `check_last_date_vs_scheduled`, `check_effective_from_required`, `check_effective_from_after_joining`, `check_effective_from_after_latest`, `check_revision_after_exit` (D36), `check_effective_from_defaulted` (info) | the seven `last_date` and `effective_from` rows, and joining_date after the first record |
| Warnings | `check_deductions_exceed_gross`, `check_bonus_above_base`, `check_deductions_above_base` (D49), `check_gross_vs_country_bounds` | deductions exceed gross; bonus above BASE; a deduction above BASE; gross below the minimum or above ten times the country median |

The header rules live here as well: the template constants, `HeaderResult` and `check_header`, whose contract is in 1.5, so every section 7 rule has one home. `messages.py` holds every template (`MSG["date_invalid"] = "{field} is not a valid date: {value}"`), so a message has one home whichever module raises it, and `msg()` repeats at most 64 characters of any value through `core.exceptions.clip`, the cut ending in `…` (D56). `validate_row(row, ctx) -> list[Message]` runs `RULES`. The API entry points build a `NormalizedRow` from plain values and run the same rules: `validate_identity(identity, ctx, employee=None)`, `validate_record(record, employee_or_country, ctx, *, is_first)`, `validate_exit(employee, last_date, ctx)`. Each raises `Invalid({field: [message]})` from the errors and returns the warnings for the response, except `validate_exit`, which returns the record that an exit before pay starts cancels, or `None` (D50). `build_context(legacy_codes=..., emails=..., employees=..., rows=...) -> ValidationContext` in `validators.py` does the queries, so the rules themselves never touch the database.

Serializers and views (`compensation/serializers.py`, `views.py`, `urls.py`): `CompensationHistoryView(ListCreateAPIView)` at `employees/<id>/compensation/`, GET returns the full history newest first as an unpaginated list (`pagination_class = None`, lines prefetched, `on` and `currency` honoured for `is_current` and `converted`), POST calls `revise` and returns 201 with the record and `warnings`. `CompensationRecordView(GenericAPIView)` at `compensation/<id>/`: DELETE calls `cancel` and returns 200 with the record. PATCH is P1 and is not registered.

### 1.5 imports

Models: SPEC section 5 "ImportBatch and ImportRow".

`imports/parser.py`:

| Function | Contract |
| --- | --- |
| `IDENTITY_COLUMNS`, `REQUIRED_COLUMNS`, `ALIASES` | the twelve identity columns in order, the ten required ones, and the alias map (`EmployeeID`, `Employee Code`, `Emp ID` and `employee_code` read as `legacy_code` when the sheet has no `legacy_code` column, matched after lowercasing and removing spaces, underscores and hyphens; with one, they get the unknown-column warning, D48). Defined in `validators.py` with `check_header` |
| `check_header(header, component_codes) -> HeaderResult` | `mapping` (sheet column index to template column), `missing`, `unknown`, `repeated` and `ambiguous`. `rejected` when anything but `unknown` is non-empty: two or more old code headers without `legacy_code`, or a template column given twice (D54). `errors()` is the 400 body, `{missing_columns, unknown_columns, repeated_columns?, ambiguous_columns?}`, each a list of section 7's messages, and `warnings` the unknown-column messages for the batch |
| `open_rows(upload, file_name, content_type) -> Iterator[list]` | `.xlsx`: `preflight_xlsx` first, then `open_workbook`, which is openpyxl's own `ExcelReader` with `read_only=True`, `data_only=True` and `keep_links=False`, its `read_worksheets` overridden to open the first worksheet alone and no chart sheet, so no part is read more than twice (D57). Then `reset_dimensions()` because the declared dimension cannot be trusted, `iter_rows(max_row=1_048_576, values_only=True)`, closed in `finally`. Anything openpyxl raises, at load, on a workbook with no worksheet or while reading, is `file is not a readable .xlsx workbook; save it again from Excel and upload it`. `.csv`: decoded as `utf-8-sig`, `csv.reader`; `UnicodeDecodeError` raises `Invalid({"file": ["file is not UTF-8"]})`, and `csv.Error` (a cell past 131,072 characters, among others) `file is not a readable .csv; save it again from Excel and upload it` (D57). Wrong extension or content type raises `Invalid({"file": [...]})` (`file must end in .xlsx or .csv, got notes.txt`, `file content type text/csv does not match .xlsx`) |
| `preflight_xlsx(stream)` | Before openpyxl opens the file (D56). Refuses an archive of more than 1,000 parts (`file holds more than 1,000 parts`, D73), then parts whose declared sizes add up to more than 50 MB (`file unpacks to more than 50 MB`); zipfile stops a part at its declared size and fails its checksum, so the declaration holds. Then streams every part through expat with no tree and with defusedxml's refusals (no entity declarations, no external entities), counting as openpyxl does: a row numbered past 1,048,576 (`row 12 is past row 1,048,576`), a cell past column 200 by its `r` or by its count (`row 12 has more than 200 cells`), more than 2,000,000 elements in all, and more than 300,000 outside cell contents and shared strings, which openpyxl builds into objects at up to 680 bytes each (both `file is too big to read`). Every part, whatever its name, so the scan never depends on finding the sheet openpyxl reads |
| `read(upload, ...) -> ParsedFile(header, rows, row_count, unnamed)` | Counts data rows while streaming, skipping rows whose cells are all blank; each row keeps its row number in the sheet, so messages point at the line the user sees. Past 15,000, the whole seeded organisation in one file (D64), it keeps counting without storing, then raises `Invalid({"rows": ["file has 15,450 data rows, limit 15,000"]})`. An empty first row is `file has no header row`. A row of more than 200 cells, the header included, is `row 12 has more than 200 cells`, the only width check a `.csv` gets (D56). `unnamed` lists the letters of columns with no header that hold data, which staging reports as ignored. The rows are read inside `contextlib.closing`, so the reader lets go of the file on every way out. A text cell longer than 256 characters is cut to 256 with an ellipsis as it is read, once for each distinct string, so a crafted sheet whose every cell points at one long shared string stays bounded at 15,000 rows. The cut cell is an error in every column, never a shorter value that passes, and a cell of nothing but spaces stays blank (D68) |
| `parse_number(cell, field) -> Decimal | Message | None` | Blank is `None`. Numeric cells become `Decimal(str(value))`. Text: currency symbols and spaces stripped; a comma is a thousands separator only with no dot anywhere and in groups ending in three digits, Western (`1,200,000`) or Indian (`12,00,000`); any other comma is the separator error; anything else that is not a plain number is `BASE must be a non-negative number, got abc` (`bonus_annual` has its own wording). Decimals are kept as given, so `check_decimal_places` reports more than two |
| `parse_date(cell, field) -> date | Message | None` | `date` and `datetime` cells (openpyxl gives `datetime`) become dates; text must be ISO `YYYY-MM-DD`; anything else, an unformatted serial number included, is `joining_date is not a valid date: 31/02/2024` |
| `normalize(row_number, cells, mapping) -> NormalizedRow` | Applies the parsers, lowercases the email and the gender, upper-cases the country code, reads a numeric `legacy_code` cell as its integer text, reads a level past 999,999 as no level (an int of thousands of digits cannot be written back as text), records `columns` and `present`, and carries every cell problem in `parse_messages`, which `check_parse_messages` reports; a BASE that is not a number is reported once, not again as missing |

`imports/services.py`:

| Function | Contract |
| --- | --- |
| `stage_upload(upload, *, actor, today=None) -> ImportBatch` | Size over 10 MB raises `PayloadTooLarge` before anything is read (the view also refuses a declared `Content-Length` over the limit, so the body is never spooled). One upload is read at a time, under a process lock taken without waiting: a second one meanwhile raises `Conflict("another file is being read; try again in a moment")`, so two of the worst files the limits allow, about 430 MB each above the process at 15,000 rows once cells are cut (D56, D68), never add up on the 1 GB machine across gunicorn's threads. A message that many rows repeat is one string and one frozen `Message`, and rows naming the same columns share one set, so 15,000 rows of the same error hold one copy of each (D68). `check_header` first: a rejected header raises `Invalid(header.errors())` and no batch exists. Every row is normalised, `build_context(rows=...)` loads what the rules need in chunked `__in` queries, and each row is validated and classified, all outside any transaction. Then one short transaction creates the batch in `review` with `warnings` (unknown columns, and headerless columns by letter), `bulk_create`s the `ImportRow`s in chunks of 1,000 and runs `recount`. Each row keeps `raw`, the cells as typed up to 256 characters (dates as ISO text, numbers as decimal text), and `normalized`, the parsed row that `row_from_json` reads back at approve, its text cut the same way. A cut value in `normalized` always belongs to a row in error, and approve reads only accepted rows (D56). The denormalised `legacy_code` and `full_name` are cut to their columns for search; a longer value is already a row error (D55). Nothing touches `Employee` or `CompensationRecord` |
| `classify(row, ctx) -> str | None` | Read after `validate_row` has set the row's flags: `None` when the code is blank or too long, `create` when unmatched, else `noop`, `revise` when amounts changed, `update` otherwise (an exit-only row is an `update`, D26). The table's error messages come from the rules themselves |
| `skip_row(batch, row)`, `unskip_row(batch, row)` | Inside one transaction, on a fresh read of the batch: `Conflict("the batch is approved, not in review")` unless it is in `review`. Skip sets `status = skipped` (skipping a skipped row changes nothing); unskip restores `status` from `validation_status`. Both call `recount`. Not audited: no pay data changes |
| `discard(batch)` | `review` to `discarded` on a fresh read, else the same `Conflict`. Not audited: no pay data changes |
| `recount(batch)` | One `aggregate` with conditional counts over the batch's rows. A no-op row counts as valid as well as no-op; a skipped row counts only as skipped |

`imports/applier.py`:

`approve(batch, *, actor, at=None, today=None) -> ImportBatch`. Everything happens inside one `transaction.atomic()`, whose `BEGIN IMMEDIATE` takes the write lock first:

1. The batch is re-read: `Conflict("the batch is approved, not in review")` unless it is in `review`, and `Conflict("3 rows have errors", error_rows=3)` (`1 row has errors`) while unskipped error rows remain.
2. The accepted rows are those with status `valid` or `warning` and action `create`, `update` or `revise`, read back with `row_from_json`.
3. `build_context(rows=...)` is built from the live tables, and `recheck_for_apply(row, ctx, action)` runs on each accepted row.
4. Each accepted row is classified again against that context. A row that a UI edit or another batch has made a no-op is left out and saved as `noop`. A row that would now apply as another action than the one reviewed is refused like a failed re-check, with `ACME-2 changed since this sheet was uploaded; upload the sheet again` (D57).
5. `bulk_apply(build_entries(...), source="import", batch=batch, ctx=ctx)` writes the rows and their audit entries.
6. `matched_employee` is set on the create rows. The counts come from the actions as they now stand: `created_rows`, `updated_rows` (identity-only and exit-only rows, D26), `revised_rows`, and `applied_rows` as their sum, and `recount` refreshes `noop_rows`. The batch becomes `approved` with `approved_at`.
7. One `import_apply` entry goes on the batch, with the counts in `after`.

When rows fail the re-check, or would apply as another action, the transaction rolls back and nothing is applied. After that, outside it, those rows become `error` with their new messages, `recount` runs, the batch stays in `review`, and the call raises `Conflict("1 row failed re-validation against current data", rows=[row numbers])`. Any other exception is logged with its traceback and leaves the batch `failed` with `error_summary = "OSError: disk full"` (type and message, at most 2,000 characters). The rows are kept, and `ApplyFailed` answers 409 with the summary.

`recheck_for_apply` (in `validators.py`) runs every rule but the warnings again and keeps the errors, against a context rebuilt from the database, so a revision or an edit made through the UI between upload and approve is seen; a row staged as `create` whose `legacy_code` an employee now holds is refused with `legacy_code HR-58213 now belongs to ACME-17; upload the sheet again` and never matched to them (D24). `build_entries` turns rows into `BulkEntry` values: a create row becomes identity plus one record; an identity-only row an update; a row with changed amounts a revise with any identity changes; a row whose `last_date` appeared or changed runs as an exit entry, which `bulk_apply` applies through the same rules as `exit_employee`. Audit entries per row follow SPEC F2: create rows write `create` on the employee and `revise` on the record, identity-only rows write `update`, revise rows write `revise` with the previous record as `before`, exit rows write `exit`; all carry `import_batch`. A row that changes identity fields or sets `last_date` as well as amounts writes its `update` or `exit` entry on the employee first and then the `revise` entry on the record, as the API path does. `updated_rows` still counts identity-only rows and `revised_rows` every row that produced a record, so the batch counts do not change.

`imports/template.py`: `build_template(country: str | None) -> bytes`, a write-only openpyxl workbook with one header row (the identity columns, then the component codes for that country in `sort_order`, or every component when omitted), the header frozen. Unknown country raises `Http404`.

`imports/samples.py` builds the rows and `imports/management/commands/make_import_file.py` is the command line over it, so the Demo data page's service calls the module and never the command (rule 1, D73): arguments as SPEC section 11, `--seed` (default 42). Rows are template-shaped and come from the live tables: `--new N` invents employees with Faker, `--raises N` takes N existing employees with every amount raised 5 percent and `effective_from` the first of the month after the reference date, `--errors N` plants one of each error in turn (negative `BASE`, malformed email, unknown department, level 9, a `31/02/2024` date, a duplicate code, a comma decimal, `HRA` on a US row), `--all` writes every existing employee unchanged.

Step 10 (D72). `make_import_file` gains `--base` (every row of `ordered_entries(10000, 42, exited=5000)` from the generator alone, no database, in joining order with the seed's legacy codes, `effective_from` at joining, leavers with their `last_date`, the current or last record's amounts and bonus, which writes `sample-data/base-15000.xlsx`), `--bonus N` (N current employees with 5 to 15% of `BASE` added to `bonus_annual`, drawn per row from `random.Random(f"bonus-{seed}")` and rounded to whole units, every other amount unchanged, `effective_from` the day given), `--promotions N` (N current employees below L6, one level up, the designation from `profiles.designation` for their department, `BASE` up 12 to 20% and every component scaled with it, `effective_from` the day given), `--exits N` (N current employees with `last_date` drawn per row from `random.Random(f"exits-{seed}")` over 14 days before the generation day to 60 days after, both ends in, and nothing else changed), `--effective YYYY-MM-DD` (the date `--raises`, `--bonus` and `--promotions` write, default the first of the month after today), `--share K` (only employees with `id % 5 == K`), and `--raises` draws 3 to 8% per row from `random.Random(f"raises-{seed}")` in place of a fixed 5%. A revision file takes the first N of its share by id among current employees whose latest live record is dated before the file's effective date, so a file regenerated after its import moves on to the next people instead of erroring on those just revised, and an exits file walks those still employed with no record dated after today, since a scheduled revision must be cancelled before an exit, draws each one's last day and keeps them when their joining date and their open record's start are on or before it, until N are picked, so every row passes the exit rules: a past last day leaves the counts at once, a future one is a scheduled exit on staff until the day. A revision file builds on each employee's latest live record, the one a revision replaces, so a raise dated after a scheduled revision scales that one instead of undoing it. The percentages are drawn in whole basis points, so no float enters the money arithmetic. `--new N` takes `--joined-after` and `--joined-until`, so newhires joined between 60 days before the generation day and 14 days after (`hire_window(today)`): `generate` draws those careers with the joining date bounded below, from the day after the date given (D69), and drawn to the last day, which keeps them after the last April review, one record each, dated at joining in the row, so a future joiner is Upcoming until the day. New joiners come from a named stream, `--stream` (default `import`), their codes drawn from `legacy_codes(offset + N, f"{stream}-{seed}", taken)` past `--offset` and their email numbers starting that far past the next id, so fix-me's joiners (`--stream newhires --offset 500`) follow newhires' 500 and the two files made from one database share no code and no email. The page's files: newhires `--new 500 --stream newhires --joined-after <today less 61 days> --joined-until <today plus 14 days>`, diwali-bonus `--bonus 1000 --share 0 --effective <today>`, april-raises `--raises 1000 --share 1 --effective <1 April next>`, promotions `--promotions 200 --share 2 --effective <today>`, exits `--exits 100 --share 3 --effective <today>`, fix-me `--raises 30 --new 20 --errors 6 --share 4 --stream newhires --offset 500`. Each is deterministic for a database, a seed and a day.

`stage_upload` refuses, after classification and before the batch is written, a file whose rows classified `create` and not in error would, with the employees in the database, leavers included, pass 25,000: `Invalid({"rows": ["No more data can be imported: this file would take ACME past 25,000 employees (now 24,900, this file adds 500)"]})`, updates and revisions not counted, and `approve` re-checks it inside its transaction with the batch's non-error create rows, a `Conflict` with the same wording, so two batches in review cannot pass it together (D72). Two rules join `validators.py`: `check_gross_not_lower` warns when a revise row's gross is below the record it replaces, `gross falls from 1,450,000.00 to 1,380,000.00 INR`, both figures to two decimals with the currency after, through the API, an import and the seed alike, and `check_noop` also marks a row a no-op when its `effective_from` and amounts repeat a live record of the employee dated that day, so a generated file imported twice changes nothing, april-raises included, whose rows are dated on the scheduled revision they made.

Serializers: `ImportBatchSerializer` (every column of the table, `uploaded_by` as the email, timestamps with `+00:00` like the rest of the API), `ImportRowSerializer` (id, row_number, legacy_code, full_name, status, validation_status, action, messages, `matched_employee` as `{id, employee_code}` or null, `raw` for the grid; `normalized` stays on the server, where only approve reads it, D56), `UploadSerializer {file}`. Views: `ImportListCreateView` (GET newest first, paginated; POST multipart, 201 with the batch), `ImportDetailView`, `ImportRowListView` (filters `status` comma-separated through `ImportRowFilterSet` and `search` over `legacy_code` and `full_name`, ordered by `row_number`, four queries with the user: the batch, the count and the page), `ImportRowSkipView`, `ImportRowUnskipView`, `ImportApproveView`, `ImportDiscardView`, `ImportTemplateView` (`?country=`, `Content-Disposition: attachment; filename="acme-import-template-IN.xlsx"`). Uploads larger than Django's in-memory threshold land in a temporary file that Django removes after the request; the parser reads the stream and nothing is ever written under the project. Accepted content types: the xlsx type for `.xlsx`, `text/csv`, `application/csv`, `text/plain` and `application/vnd.ms-excel` (what Windows with Excel installed calls a `.csv`) for `.csv`, plus `application/octet-stream`, or no type at all, when the extension is right.

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
    local: bool = False    # currency=local was asked for, so no rate is used
```

`build_filters(lookups, *, country, department, include_exited, on, currency)` makes them. `Lookups` holds every country and department by code in name order, loaded once per request; a code in the filter that names neither is a 400 with section 7's own words (`Unknown country_code: XX`, `Unknown department: growth`), since the per-country and per-department insights list every code in the filter. A code given twice counts once.

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

Each insight is `def <name>(f: InsightFilters, rates: fx.RateTable, lookups: Lookups) -> dict`, registered in `INSIGHTS`. Sums and counts: `population(f).values(<group fields>, "currency_code").annotate(n=Count("id"), total_cost=Sum("total_cost_annual"), gross_sum=Sum("gross_annual"))`, then in Python per group `total_cost = q2(sum(total_cost_ccy * rates.rate(ccy, f.currency)))` and `mean_gross = q2(sum(gross_sum_ccy * rate_ccy) / n)`. Medians and percentiles: `population(f).values_list("gross_annual", "currency_code", <group field>)`, each value converted as `q2(v * rate)`, then `statistics.median` and `statistics.quantiles(values, n=100, method="inclusive")` (p1 is index 0, p10 index 9, p25 index 24, p50 index 49, p75 index 74, p90 index 89, p99 index 98), each result passed through `q2`. Guards: zero values gives `None`; one value gives that value for every percentile. The small-group rule (D59): a group with fewer than `SMALL_GROUP = 5` people, the whole population included, publishes `headcount` alone, with `None` for total cost, share, mean and median, applied on every card by `published(group, values, *, mean=False)`. The spread figures need `SPREAD_GROUP = 20` people and are `None` below that: by-level's percentiles and the distribution's `p1`, `p99`, `bands` and `markers`. The two constants in `insights/queries.py` are the only spellings of the thresholds, and `components/insights/figures.ts` mirrors them. Empty groups are listed with `headcount 0` and `None` elsewhere. Output shapes, with money as two-decimal strings after `core.money.render`:

| Insight | Shape |
| --- | --- |
| `summary` | `{currency, rate_month: {label, effective_from}, headcount, total_cost, mean_gross, median_gross, countries, departments}` |
| `by-country` | `{..., rows: [{country: {code, name}, headcount, total_cost, median_gross, share_pct}]}` sorted by `total_cost` descending, every country in the filter listed; `share_pct` is `total_cost / overall total_cost * 100` to one decimal, and `None` with the total under five people, since the share times the overall total gives the total back |
| `by-department` | `{..., rows: [{department: {code, name}, headcount, total_cost, mean_gross, median_gross}]}` sorted by `total_cost` descending, every department in the filter listed, all twelve without one |
| `distribution` | `{..., headcount, p1, p99, bands: [{index, from, to, count}], markers: {p10, p50, p90}}`. `width = (p99 - p1) / 12` unquantised; band `i` is `[p1 + i*width, p1 + (i+1)*width)`, the last band closed at `p99`; a value maps to `floor((v - p1) / width)` clamped to 0 and 11, so values outside `p1..p99` land in the end bands, computed by `band_of(v, p1, p99)` as `floor((v - p1) * 12 / (p99 - p1))` so a value on a band's lower edge lands in that band, which a rounded width would miss; `p1 == p99` gives one band `{from: p1, to: p1, count: n}`; under twenty people `p1`, `p99`, `bands` and `markers` are all `None` (D59) |
| `by-level` | `{..., rows: [{level, headcount, p10, p25, median, p75, p90}]}` for levels 1 to 6; under twenty people all five figures are `None`. Never min or max, each of which is one person's pay (SPEC section 9, D25, D59) |
| `gender-gap` | `{..., rows: [{country: {code, name} | null, female: {headcount, median_gross}, male: {headcount, median_gross}, other_count, undisclosed_count, gap_pct, reason}]}`, one row per country in the filter, in name order, and a final row with `country: null` for overall. `gap_pct = (median_male - median_female) / median_male * 100` to one decimal; `None` with the reason `fewer than 5 women`, `fewer than 5 men` or both when either gender has fewer than five people (`group too small` until step 8, D62), and a gender under five shows its headcount with `median_gross: None` |

`rate_month` is `{label: rates.month_label(currency), effective_from: rates.month_of(currency)}` where the month is that of the most recent `effective_from` among the rates used for the reporting currency; with `currency=local` the label is `fx.local_label`'s `"local currency (INR)"` and `effective_from` is `None`, even when the local currency is one the toggle also offers (D58). Rows with equal total cost follow in name order, and the rows that show their headcount alone, the empty ones among them, come after the rest in name order (`by_cost`), so the order never hints at a withheld total (D59).

`insights/views.py`: `InsightView(APIView)`. Unknown name is 404. Parses `country` and `department` with `parse_csv`, `include_exited` with `parse_bool` (default false, any other word a 400), `on` with `parse_on`, and hands them with `currency` to `build_filters`, which resolves it with `fx.resolve_reporting_currency`. Loads one `RateTable`, calls the query, returns `Response(render(payload))`. No DRF serializer: the shapes above are the contract and `frontend/src/api/types.ts` mirrors them. Queries per request: the user, the countries, the departments, the rates, then at most one aggregate and one `values_list`. Six at most, pinned.

#### Added in step 8 (D62)

`trend` and `cost-bridge` count the people employed on each date, read from `spans` below rather than `population(f)`, the one exception to the bar deciding who is counted: Include exited does not apply to them, so someone who left by a date is not counted there and someone who left during the bridge's year is a leaver. When the box is ticked each card says so in a caption, `Counts people employed on each date; Include exited doesn't apply` (D62).

`spans(f, first, last)` is the dated population both share: one query of the live records of the filtered employees that can count on some day in `[first, last]` (`effective_from <= last`, and `effective_to` null or after `first`), as `values_list("employee_id", "currency_code", "total_cost_annual", "effective_from", "effective_to", "employee__joining_date", "employee__last_date")`. In Python each row becomes the days it counts on: from the later of `effective_from` and `joining_date` up to the earlier of `effective_to` and `last_date + 1`, the days that employee is employed and the record current.

`month_ends(on) -> list[date]`: the 24 month-ends `d` with `on - 24 months < d <= on`, oldest first, so 31 Oct 2024 to 30 Sep 2026 for 7 Oct 2026, ending at `on` itself when `on` is a month-end.

`trend(f, rates, lookups, *, measure)`: headcount and total cost per currency at each month-end by a running sum over the sorted dates (a span adds at the first date it covers and drops after its last), converted with the one `RateTable` for `f.on` and quantised once per date. `{currency, rate_month, measure, latest, points: [{month_end, headcount, total_cost}]}` with `total_cost` `None` under five people on that date and `latest` the last month-end, which the card names. `measure` is `total_cost` or `headcount`. Both figures are always in the payload and in the export, and `measure` only picks the line drawn.

`cost_bridge(f, rates, lookups)`: from `s`, the same day a year before `on` (28 February for 29 February), to `e` = `on`, read from `spans(f, s, e)`. Each employee's total cost on `s` and on `e`, at the rates for `on`: leavers count on `s` and not `e`, joiners on `e` and not `s`, stayers on both. Start, leavers, joiners and end are each summed per currency, converted and quantised once, and pay changes is `end - start + leavers - joiners` on those quantised figures, so the five parts add up to the cent and pay changes takes any sub-cent rounding. Pay changes is also summed directly from the stayers, end minus start for each, per currency, converted and quantised once, and a test holds that figure within 3 cents per currency in the filter of the balancing one, which the card and the export show (D62). `{currency, rate_month, start_date, end_date, parts: [{part, people, amount, reason}]}` for `start`, `leavers` (a negative amount), `joiners`, `pay_changes` and `end`. Start and end each need five people (D59). When leavers, joiners or stayers number 1 to 4, each of the three with people in it shows them alone with `amount: None`, the short one carrying `fewer than 5 people` and the others `withheld with the leavers` (or `joiners`, or `pay changes`, whichever is short first), while start and end stay shown. A part of 0 people shows `0.00` and triggers nothing (D62).

`by_tenure(f, rates, lookups, *, level)`: the population on `on`, one level unless `level` is `all`. Tenure is the completed years from `joining_date` to `on`, or to `last_date` for someone who left, counted on anniversaries (29 February's falls on 28 February in other years). Bands `under_1`, `1_to_3`, `3_to_5`, `5_to_10` and `10_plus`, each from its lower bound up to but not including its upper one. `{currency, rate_month, level, rows: [{band, label, headcount, median_gross}]}`, `median_gross` `None` under five.

`cost_mix(f, rates, lookups, *, view)`: per country in the filter, all six without one, in name order, from two aggregates: the population's `CompensationLine` amounts, and how many hold each (`annual_amount > 0`), summed per country, currency and component, and its records' bonus, how many have one, gross and total cost summed per country and currency. `view=cost`: `BASE`, each of the country's other earning components by `sort_order`, `BONUS` and the employer contribution, as shares of total cost. `view=take_home`: `NET` (gross minus deductions) and each deduction by `sort_order`, as shares of gross. Each share is quantised to one decimal on its own, so a bar can add to 99.9 or 100.1. `{currency, rate_month, view, segments: [{code, name}], rows: [{country: {code, name}, headcount, segments: [{code, name, share_pct}] | None, reason}]}`. A country's `segments` are `None` with `reason` `fewer than 5 people` under five, and with `<segment name> held by fewer than 5 people` when a segment its bar shows is held by 1 to 4 people, since that share times its total cost on by-country gives back what they are paid (D62). A country with nobody has no reason. The top-level `segments` lists every segment of the bars shown in the one order they stack: earnings by `sort_order`, `BONUS`, then the employer contribution, or `NET` then each deduction. Shares do not depend on the reporting currency, which the export still names.

`gender_gap(f, rates, lookups, *, view)`, `view` `pay_gap` (the payload above), `bonus`, `quartiles` or `by_level`. A short comparison's reason is `gender_reason(women, men)`: `fewer than 5 women`, `fewer than 5 men`, or `fewer than 5 women and fewer than 5 men`, in place of `group too small` in every view, and a group with nobody in it has none (`group_reason`). Under the owner's rule at the step 8 close, the views publish counts, shares, medians and gaps, never a mean amount, which adds up across rows and could give a withheld one back (D62).
- `bonus`, per country in the filter in name order and then overall: per gender `{headcount, receiving, receiving_pct, median_bonus}`, a bonus counted when `bonus_annual > 0` in its own currency and converted per value, and `mean_gap_pct` and `median_gap_pct`, each `(men - women) / men * 100` to one decimal, the means unrounded and never published. The receiving shares need 5 women and 5 men in the group. The median bonus and the gaps need 5 women and 5 men receiving a bonus, and say `fewer than 5 women with a bonus` and the like.
- `quartiles`: the women and men in the filter ranked by gross in the reporting currency, ties by employee id, cut at `floor(k * n / 4)` for k = 1 to 3, the lowest quartile first. `{headcount, other_count, undisclosed_count, quartiles: [{quartile, headcount, female, male, female_pct, male_pct}] | None, reason}`, `headcount` the women and men ranked and the other two counted once beside, never ranked. It needs 20 women and men, 5 of each, and below that shows the headcount with the reason, none when nobody is ranked.
- `by_level`, per country in the filter in name order and per level 1 to 6: `{rows: [{country, level, female: {headcount, median_gross}, male: {headcount, median_gross}, mean_gap_pct, median_gap_pct, flagged, reason}], others: [{country, other_count, undisclosed_count}]}`, `flagged` true when the mean gap before rounding is 5% or more either way. The medians and gaps need 5 women and 5 men in that country and level. Other and undisclosed are counted per country beside the levels, never per level.

`answer()` reads each card's control from `CONTROLS = {"trend": ("measure", ("total_cost", "headcount")), "by-tenure": ("level", ("all", "1", "2", "3", "4", "5", "6")), "cost-mix": ("view", ("cost", "take_home")), "gender-gap": ("view", ("pay_gap", "bonus", "quartiles", "by_level"))}`, the first value being the default. It is read by `core.filters.parse_choice` in any case, and anything else is a 400 in section 7's form, `measure must be total_cost or headcount, got x`. The export's JSON filters carry the control as the insight applied it, its default when none was given, and leave Include exited out for `trend` and `cost-bridge`, which it does not apply to (D62). `on` before 1900-01-01 is a 400, since both reach two years back from it. Queries per request are pinned in the tests: the user, the countries, the departments, the rates and one or two of the insight's own. `timing` times each new insight, and every value of every control besides its default.

#### Added in step 9 (D64)

The insights read a period. `InsightFilters` gains `start` and `end` in place of `on`, and `views.answer()` parses `from` and `to` with `core.dates.parse_period`. `to` defaults to today in UTC and `from` to the first day of the 12 months ending on it (`period_start`, the day after `months_before`), the dashboard's Last 12 months, never before `REPORTING_START`, so a request without them returns the dashboard's default (D69). Each must be a date from 2020-04-01, the reporting cut-off in `core.dates.REPORTING_START`, the start of FY 2020-21, to 2100-12-31, with `from` on or before `to`, else a 400 in section 7's form: `from must be on or after 2020-04-01, got 2020-03-31`, `to must be on or before 2100-12-31, got 2101-01-01`, `from must be on or before to`. The cut-off bounds the period's dates and nothing else: records are never filtered by `effective_from`, so a record that started before it counts for the days it covers, and with Include exited `population` adds only those whose `last_date` is on or after it (D70). The insights no longer read `on`. One `RateTable`, loaded for `end`, converts every figure of every card, and `rate_month` names it. Every payload's header names the period, `{from, to, currency, rate_month}`.

`population(f)` reads `f.end`, so every card built on it (summary's headcount, mean and median, by-country, by-department, distribution, by-level, by-tenure, cost-mix and gender-gap) shows the state on `to`, and the card says so. Level and designation are the employee's own, today's or the last day's, so on an earlier `to` these cards group people by that level, and the three that group by level (by-level, by-tenure's Level control and gender-gap's By level) say so when `to` is not today: `Levels are as of today; anyone promoted after <to> appears at their new level` (D64).

`trend` reads `spans(f, f.start, f.end)` and gives a point at `f.start`, one at each month-end after it and before `f.end`, and one at `f.end`, a month-end `start` or `end` not repeated. Each point is `{date, headcount, total_cost}`, `date` in place of `month_end` since the first and last need not be month-ends, at the one rate, `total_cost` `None` under five, and `latest` goes, since the last point is `to`. The dates come from one pass over the spans and the sorted dates, as now, so the longest period, 1 April 2020 to 2100, about 970 points, stays one query (D70).

`cost_bridge` runs from `f.start` to `f.end`, so its start and end equal trend's first and last points, which a test holds. Its rules stay as D62 has them.

`summary` adds what the period cost, from the same spans: each record's annual total cost times the days it was current within `[start, end]`, a day costing the annual figure divided by the days in its calendar year, 365 or 366, summed per currency, converted once and quantised once. `{..., spent: {headcount, total_cost}}`, `headcount` being everyone employed on any day of the period and `total_cost` `None` when 1 to 4 people were employed on any day of it, since that day's cost is part of the total and two totals, or one and trend's points, would give it back (D59, D68). Include exited does not apply, as for trend. The KPI card that showed the total is labelled `Annual cost on <to>`.

Queries per request stay pinned. `timing` times each insight on the default period, and the summary, trend and the bridge, whose work grows with the period, on each preset and on 1 April 2020, the reporting cut-off, to today (D69, D70). `--insights periods` times those alone, and `--case import --sheet crafted` stages the worst sheet the limits let through, every cell of 15,000 rows one 10,000-character shared string, rolled back, so both run on Fly's shared CPU without spending its burst balance on the rest (D65, D68).

### 1.7 exports

`exports/writers.py`: `escape_cell(value)` prefixes a single quote when a text cell starts with `=`, `+`, `-`, `@`, tab or carriage return, and the CSV writer alone also puts one after any `;` inside a text cell that one of them follows, directly or after one double quote, since a reader whose list separator is `;` splits the cell there and takes the doubled quote for an empty quoted start (D76) (numbers are written as numbers and are never escaped, and JSON values are not escaped, since only a spreadsheet runs a cell, D60); `csv_stream(header, rows) -> Iterator[bytes]` writes a hundred rows a chunk through `csv.writer` over an echo object, as Django's streaming example does, every field quoted, UTF-8 with a BOM so Excel opens it correctly; `xlsx_bytes(header, rows, *, sheet) -> bytes` reads the rows first, then uses a write-only workbook and `ws.append`, amounts as numbers and dates as dates, and replaces what XML 1.0 cannot hold (the C0 controls but tab, newline and carriage return, and U+FFFE and U+FFFF) with U+FFFD, where openpyxl would refuse the workbook or write one that will not open. The write-only mode spools the sheet to a temporary file it removes on save, and reading the rows first means a failing row fails before that file holds pay; `json_bytes(keys, rows, *, generated_at, filters) -> bytes`.

`exports/tables.py`: `Table(header, keys, rows)`. `directory_table(employees, *, on, rates, currency)` takes the queryset the view has filtered through `DirectoryMixin`, the list's own filters, search and ordering, checks first that every currency a live record is in has a rate (a `MissingRate` 400 before the CSV's 200, never a file cut off part way), and iterates it with `.iterator(chunk_size=1000)` (prefetches are honoured chunk by chunk), yielding the seventeen columns of SPEC F6 in order, the reporting column headed with its currency (`Gross (USD)`), department and country by name, the amounts and the record's date and version from the shown record, and no amounts for someone with no live record (D50). `INSIGHT_TABLES = {"summary": ..., "by-country": ..., "by-department": ..., "distribution": ..., "by-level": ..., "gender-gap": ...}`, each turning the insight's dict, before rendering, into a `Table`: `summary` one row of Headcount, Total cost, Mean gross, Median gross, Countries, Departments; `by-country` Country code, Country, Headcount, Total cost, Median gross, Share %; `by-department` Department code, Department, Headcount, Total cost, Mean gross, Median gross; `distribution` Band (from 1), From, To, People; `by-level` Level, Headcount, p10, p25, Median, p75, p90; `gender-gap` Country code, Country (`Overall` for the last group), Gender (female, male, other and undisclosed, the last two never with a median), Headcount, Median gross, Gap %; each followed by Reason, Currency and Rates, which a test holds every insight to. Reason is `fewer than 5 people` or `fewer than 20 people` when the API withheld a figure from someone, empty otherwise, and gender-gap's own reason, `fewer than 5 women`, `fewer than 5 men` or both from step 8 (`group too small` before it, D62), on each row of its group. A distribution without bands is one row of its headcount (D60).

`exports/views.py`: `ExportEmployeesView(DirectoryMixin, GenericAPIView)` and `ExportInsightView(APIView)`, which reads through `insights.views.answer(name, params)`, the insight endpoint's own parsing. An unknown insight is 404 before anything else is read. `file` must be `csv`, `xlsx` or `json`, in any case, else 400 `file must be csv, xlsx or json, got pdf`. CSV is a `StreamingHttpResponse` whose first hundred rows are read before the 200 goes out, so a failing query is an error response; XLSX and JSON are built whole before they are sent (the 10,000-row directory is 0.9 MB of XLSX and 4.3 MB of JSON). `Content-Disposition: attachment; filename="acme-employees-20261007-0930.csv"`, or `acme-by-level-20261007-0930.xlsx` for an insight, the timestamp in UTC, and the XLSX sheet named `employees` or after the insight. JSON is `{"generated_at", "filters", "rows": [{key: value}]}` with snake_case keys (D27), `filters` holding the filters the export reads, as given, each comma-separated value clipped on its own to 64 characters (D68, D73), with `on` and `currency` as applied, and nothing it does not read, so `file`, `page`, `page_size` and a stray parameter are left out (D60). Queries: the directory export reads the user, the rates, the currencies of the live records, the employees and one records prefetch a chunk; an insight export reads what its insight reads.

Added in step 8 (D62), each ending with Reason, Currency and Rates like the rest: `trend` one row per month-end (Month-end, Headcount, Total cost, whatever the measure); `cost-bridge` one row per part (Part, Date for start and end, People, Amount); `by-tenure` one row per band (Tenure, Headcount, Median gross), the level in the JSON filters; `cost-mix` one row per country and segment (Country code, Country, Headcount, Segment, Share %), a withheld country one row of its headcount with the card's reason; and gender-gap one table per view, `bonus` one row per group and gender (Country code, Country, Gender, Headcount, Receiving, Receiving %, Median bonus, Mean gap %, Median gap %), `quartiles` one row per quartile of women and men (Quartile, Headcount, Women, Men, Women %, Men %, Other not ranked, Undisclosed not ranked), or one row of the headcount when withheld, and `by_level` one row per country and level (Country code, Country, Level, Women, Women median, Men, Men median, Mean gap %, Median gap %, Flag, Other in country, Undisclosed in country). No table carries a mean amount (D62).

Step 9 (D64): an insight export reads `from` and `to` as its insight does, and its JSON filters name both as applied, beside `currency`, never `on`. trend's table is one row per point (Date, Headcount, Total cost), and the summary's table adds Spent in period and People in period, its Reason `fewer than 5 people on a day in the period` when the spend alone is withheld (D68). The directory export keeps `on` and reads `status` as the directory does, so without `status` it holds the 10,000 active employees, and its JSON filters name the status it applied.

### 1.8 audit

Model: SPEC section 5 "AuditLog". `entity_type` values: `employee`, `compensation_record`, `import_batch`, `exchange_rate`, and `demo_database` with id 0 for the one `demo_reset` entry a reset writes (D72).

`audit/services.py`: `record(action, *, entity, actor, before, after, employee=None, import_batch=None, at=None) -> AuditLog` (`at` defaults to now; the seed passes the reference datetime); `bulk_record(entries: list[AuditLog]) -> None` in chunks of 1,000; `snapshot_employee(employee, shown_record=None) -> dict` and `snapshot_record(record, lines=None) -> dict`. The snapshots mirror the detail serializers field for field, minus the request-dependent keys (`converted`, `is_current`, `is_scheduled`, `shown_label`, `status`), rendered JSON-safe with `core.money.render`. They are plain functions rather than DRF serializer calls so the seed can produce 40,000 of them inside its 60 s budget, and `tests/audit/test_snapshots.py` asserts `snapshot_record(r) == CompensationRecordSerializer(r, context=...).data` minus those keys, so the two cannot drift. Converted amounts never enter an audit row (rule 3).

### 1.9 seed

Section 5.

### 1.10 demo

Step 10 (D72). `apps/demo`, mounted at `/api/v1/admin/`.

`demo/services.py`:

| Function | Contract |
| --- | --- |
| `PAY_TABLES` | `seed.profiles.PAY_TABLES`, the first six of `BUSINESS_TABLES` in truncation order: `audit.AuditLog`, `compensation.CompensationLine`, `compensation.CompensationRecord`, `imports.ImportRow`, `imports.ImportBatch`, `employees.Employee`. Lookups, rates and users are never in it |
| `counts() -> dict` | `{employees, compensation_records, compensation_lines, import_batches, import_rows, audit_entries}`, one `count()` each, what the dialog shows and the reset returns |
| `reset_demo(*, actor, password, confirm) -> dict` | `actor.check_password(password)` and `confirm == "RESET"` first, both checked, so a 403 names every wrong field: `Forbidden({"password": ["password did not match"], "confirm": ["type RESET to confirm"]})`. Then the import lock, taken without waiting through `imports.services.reading_lock()`: `Conflict("an import is being read; try again in a moment")` when it is held. Then one `transaction.atomic()`, whose `BEGIN IMMEDIATE` waits up to SQLite's 20 s for an approve in flight and whose `database is locked` error is caught and answered `Conflict("an import is being applied; try again in a moment")`: the counts, `seed_data.truncate(PAY_TABLES)`, which deletes in that order and clears each table's `sqlite_sequence` row so the next employee is ACME-1 and the next record id 1, and one `audit.record("demo_reset", actor=actor, employee=None, before=counts, after={})`, the one row the audit log then holds. Returns the counts |
| `SAMPLE_FILES` | the seven files in page order, each `(name, file_name, description, generated)`: `base` (`base-15000.xlsx`, read from `settings.SAMPLE_DATA_DIR`), `newhires`, `diwali-bonus`, `april-raises`, `promotions`, `exits`, `fix-me` |
| `sample_file(name, *, seed, today) -> tuple[str, bytes]` | the file name and its bytes: the base file from disk, the rest built in memory by `imports/samples.py`, the module `make_import_file` wraps, with the options in 1.5 and the day `today`, so a download is one request. An unknown name is `Http404`, a generated file on an empty database `Conflict("import the base file first")` |

`demo/views.py`: `ResetDemoView` (GET the counts; POST through `ResetSerializer {password, confirm}`, both required strings, blank allowed so that anything but the password and RESET is the service's 403, throttled by `ResetRateThrottle`, scope `reset` at `5/hour`, keyed on the client address like the login throttle by overriding `get_cache_key`, since DRF keys an authenticated request on the user, so wrong passwords count and one reviewer's attempts never block another), `SampleFileListView` (`{employees, files: [{name, file_name, description, available}]}`, `available` false for a generated file while `employees` is 0), `SampleFileView` (`?seed=`, default 42, a value that is not a whole number a 400 `seed must be a whole number`, the attachment with the xlsx content type and `Content-Disposition`). The approve in `imports/applier.py` answers a `database is locked` error the same way the reset does, a 409 `an import is being applied; try again in a moment` that writes nothing, since a second approve from a reload while a cut one still runs waits out SQLite's lock, and it marks a batch `failed` only while that batch is still in review, so the first approve's result stands. `demo/urls.py`: `admin/reset-demo/`, `admin/sample-files/`, `admin/sample-files/<name>/`. `AuditLog.Action` gains `DEMO_RESET = "demo_reset"`, a choices-only migration. `seed_data.truncate_business_tables()` becomes `truncate(labels)` over any list of table labels, and the seed passes `BUSINESS_TABLES` as before, so the reset and the seed delete through the one function (CLAUDE.md rule 6).

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
  V->>V: a declared Content-Length over 10 MB answers 413, the body never spooled
  V->>S: stage_upload(upload, actor)
  S->>S: size over 10 MB raises 413, an upload while another is read raises 409
  S->>P: read(upload): header, rows, row_count
  P->>P: .xlsx: preflight_xlsx before openpyxl (1,000 parts, 50 MB unpacked, a row past 1,048,576 or 200 cells, 2,000,000 elements, 300,000 outside cells)
  P->>P: open_workbook: the first worksheet alone, no chart sheet, no external link
  P-->>S: rows, or 400 for encoding, extension, size, width or row limit
  S->>VA: check_header(header, component codes)
  alt header rejected
    S-->>V: Invalid {missing_columns, unknown_columns, repeated_columns?, ambiguous_columns?}
    V-->>B: 400, no batch created
  end
  S->>P: normalize(cells) for every data row
  S->>DB: build_context: countries, departments, components, matched employees, their records and lines, emails in use
  loop every data row
    S->>VA: validate_row(row, ctx)
    S->>S: classify(row, ctx) -> create, update, revise, noop or None
  end
  S->>DB: one transaction: INSERT ImportBatch(status=review, warnings), bulk_create ImportRow in chunks of 1,000, recount
  V-->>B: 201 batch summary
  B->>V: POST rows/{rowId}/skip/ or unskip/
  V->>S: skip_row or unskip_row (409 unless review), recount
  B->>V: POST /imports/{id}/discard/
  V->>S: discard (409 unless review)
  B->>V: POST /imports/{id}/approve/
  V->>A: approve(batch, actor)
  A->>DB: BEGIN IMMEDIATE (transaction.atomic)
  A->>A: the batch re-read: 409 unless review, 409 while unskipped error rows remain
  A->>VA: build_context from the live tables, recheck_for_apply on every accepted row
  A->>A: classify every accepted row again: a no-op left out, another action than reviewed refused as a failed re-check
  A->>C: bulk_apply(entries, source=import, batch)
  C->>VA: validate every entry
  C->>DB: bulk_create employees, records, lines; bulk_update closed records and identity changes
  C->>AU: bulk_record create, update, revise, exit and cancel (D50) entries with import_batch
  A->>AU: record(import_apply, batch, after=counts)
  A->>DB: batch approved, counts, COMMIT
  alt re-validation failed
    DB-->>A: ROLLBACK
    A->>DB: rows re-marked error, recount, batch stays in review
    V-->>B: 409 with the rows
  else any other exception
    DB-->>A: ROLLBACK
    A->>A: logger.exception with the traceback
    A->>DB: batch failed with error_summary, rows kept
    V-->>B: 409 with error_summary
  end
  V-->>B: 200 batch summary
```

Memory at the peak: 10,000 `NormalizedRow` and `ImportRow` objects live at once before the chunked `bulk_create`, each with two JSON blobs; tens of megabytes, measured by `/perf-timing` in step 5 against the 1 GB machine. What a hostile file could cost inside openpyxl is bounded before openpyxl opens it (D56): the review's far-row, wide-row and 5-million-cell files, and two of 12 million elements, are refused in under a second at 67 MB.

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
6. Exit closes the open live record at `last_date + 1 day` after the checks in 1.3. A future `last_date` is a scheduled exit and closes the record immediately with a future `effective_to`. An exit dated before the only live record starts, a record that has never been current, cancels that record instead, which leaves the employee with no live record (D50).
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
    def month_of(self, to_currency: str) -> date | None
    def month_label(self, to_currency: str) -> str
    def rows(self) -> list[dict]

LOCAL = "local"
def asks_local(currency: str | None) -> bool
def local_label(currency: str) -> str
def resolve_reporting_currency(currency: str | None, country_codes: Sequence[str], countries: Mapping[str, Country]) -> str
```

- `load(on)` reads every `ExchangeRate` row in one query and keeps, per pair, the row with `effective_from <= on < effective_to` (or open), else the row with the smallest `effective_from`. That is SPEC section 4 rule 4: a month per row, the earliest rate before the first month, no 422.
- `rate(a, b)`: `1` when `a == b`; the direct row when the pair exists; otherwise through USD: `rate(a, "USD") * rate("USD", b)`, where a missing `USD -> b` row falls back to `1 / rate(b, "USD")`. Nothing is quantised here. A pair that cannot be resolved raises `MissingRate`, a `DomainError` mapped to `400 {"currency": [...]}`; it is unreachable with the seeded pairs and exists so the failure is explicit.
- `effective_from(a, b)`: `None` for identity, the row's date for a direct pair, the later of the two legs for a routed one.
- `convert(amount, a, b) = q2(amount * rate(a, b))`.
- `case_expression(to, field)`: `Case(*[When(**{field: ccy}, then=Value(self.rate(ccy, to))) for ccy in currencies], default=Value(Decimal("1")), output_field=DecimalField(18, 8))`, built from the six seeded currencies. Used only by the directory annotation to order and filter.
- `month_of(to)`: the most recent `effective_from` among the rates into `to`, `None` when no rate feeds it. `month_label(to)`: "October 2026 rates" from that month, and `local_label(to)` when no rate feeds it.
- `asks_local(currency)`: whether a request's `currency` is `local`, in any case. `local_label(currency)`: `"local currency (INR)"`, the label of figures that no rate has converted.
- `resolve_reporting_currency`: `usd` or `None` gives `USD`, `eur` gives `EUR`, `local` gives the one filtered country's `currency_code` and raises `Invalid({"currency": ["currency=local needs exactly one country in the filter"]})` for any other count; anything else is `Invalid`.

`set_exchange_rate(from_currency, to_currency, rate, effective_from, *, actor=None, replace=False) -> ExchangeRate` in `core/services.py`, used by the management command and `ensure_rates`: `effective_from.day != 1` raises `Invalid({"effective_from": ["must be the first day of a month"]})`; `rate <= 0` or identical currencies raise `Invalid`; with an open row for the pair, a date before it raises `Invalid({"effective_from": ["on or before the latest row 2026-10-01"]})`; the same date raises `Invalid({"effective_from": ["a rate for October 2026 exists, pass --replace"]})` unless `replace`, in which case the existing row's `rate` is updated; otherwise, in one transaction, the open row's `effective_to` becomes the new date, the new row is inserted open-ended, and audit `set_rate` is written on the new row with the closed row's snapshot as `before`. The command is `set_exchange_rate FROM TO RATE --effective-from YYYY-MM-01 [--replace]`.

Where conversion happens: the directory annotation (`case_expression`, for ordering and filtering only), the list and detail serializers (`convert` per shown record), the insight queries (section 1.6), and the export tables (`pick_shown` and `rates.convert`, the values the serializers show). Never in a model, never stored.

## 5. Seed

`seed/profiles.py` holds every design parameter from SPEC section 11 as plain data: `COUNTRIES` (code, name, currency, share, level-3 anchor, minimum gross, the country's components with their share of base, employer contribution share), `DEPARTMENTS` (code, name, share, pay multiplier), `LEVELS` with `LEVEL_SHARES` and `LEVEL_MULTIPLIERS`, the designations by level, `TAX_SHARE_BY_LEVEL` (levels 1 to 2 at 10 percent of gross, 3 to 4 at 20, 5 to 6 at 30), the bonus share and range, `GENDER_SHARES` (48, 50, 1, 1), `REFERENCE_DATE = date(2026, 10, 6)`, `REFERENCE_DATETIME = datetime(2026, 10, 6, tzinfo=UTC)`, `RATES` (sixteen rows) and `NOISE_SIGMA = 0.18`. Since step 9 (D64) it also holds `ACTIVE_EMPLOYEES = 10_000`, `EXITED_EMPLOYEES = 5_000`, `HISTORY_START = date(2015, 1, 1)`, `MIN_TENURE_DAYS = 30`, `LADDER = {1: (0, 3), 2: (3, 6), 3: (5, 8), 4: (7, 11), 5: (10, 13), 6: (12, 30)}` in years of total experience, `LEAVE_WEIGHTS = {1: 2, 2: 1.5, 3: 1, 4: 1, 5: 1, 6: 1}`, `RAISE_RANGE = (0.03, 0.08)`, `PROMOTION_RANGE = (0.12, 0.20)`, `EXPERIENCE_PAY = 0.02` and `EXPERIENCE_PAY_CAP = 0.20`.

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

The random streams are one `random.Random(seed)` for those who stay and one `random.Random(f"{seed}-leavers")` for those who left, each with one `Faker(locale)` per country locale (`en_IN`, `en_US`, `en_GB`, `de_DE`, `nl_NL`; Singapore draws from `en_US` because Faker has no Singapore locale, D35) seeded the same way. The generator never reads the global `random`, never iterates a set or dict in insertion-insensitive order, and draws each person's values in a fixed sequence: country, department, gender, name, level, experience, joining date, promotion points, noise, bonus, jitter, raises. Experience and dates are whole days, a year being 365.25 of them. Emails are `f"{first}.{last}.{n}@acme.example"` lowercased with a running number, so they are unique by construction. `ordered_entries` sorts everyone by joining date, leavers among them and ties in generation order, so the database numbers them from ACME-1, the earliest joiner, and gives each a `legacy_code` of `HR-` and five digits drawn without repeats by a generator of its own, so the employee draws are unchanged (D48).

Generation (`seed/generator.py`, `generate(active, seed, *, exited=0, start_number=1) -> Iterator[BulkEntry]`), each person drawn from their last review backwards (D64):

1. Those who stay come first. Level by `LEVEL_SHARES`. Experience at the last review, which is 1 April 2026, or the joining date for someone who joined since or in the six months before it (D70), uniform over the level's range in days. The joining date is uniform between the later of 1 January 2015 and that review less that experience, and the reference date, so years at ACME never exceed total experience. Every active L1 therefore joined after 1 April 2023.
2. Leavers. Their 5,000 last days are spread over the months from January 2015 to September 2026 in proportion to everyone employed at each month's end, by largest remainder so the total is exact. Who is employed depends on the leavers themselves, so the spread is settled in three passes, the first on those who stay alone. The day is uniform within its month and at least 30 days after 1 January 2015. Then a level by `LEVEL_SHARES` times `LEAVE_WEIGHTS`, experience at the last review before the last day, raised where needed so they can have stayed 30 days, and a joining date as for those who stay, at least 30 days before the last day. With 10,000 who stay and 5,000 who leave, each year's leavers come to a steady 11% of its headcount, which the owner kept over a smaller count (D64).
3. The level path. Their reviews are the joining date and each 1 April after it, but the first when they joined in the six months before it, from 1 October on: that April brings no raise and no promotion, and when it was the last April the last review is the joining date (D70). Each person draws one promotion point inside each overlap, in days: L2 at 3 years exactly, L3 between 5 and 6, L4 between 7 and 8, L5 between 10 and 11, L6 between 12 and 13. The points for their own level and the next are drawn either side of their experience at the last review, so the path ends at the level drawn. Their level at joining and at each review after it is the highest whose point their experience has passed then, so a promotion lands on the first review at or past its point. The windows lie at least 366 days apart, so no one moves two levels at once, but a skipped April leaves 12 to 18 months before the first review, room for two points, and then the lower moves to the joining day, still inside its window since the windows start at least 730 days apart (D70).
4. Pay at the last review, today's record or the last day's: base = anchor times the level multiplier, the department multiplier, lognormal noise and 1 plus 2% a year of experience above the level's floor (at most 20%), rounded to 100 and raised if need be so gross reaches the country's minimum. Each component is its share of base (or of gross for `TAX`) times a per-employee jitter between 0.95 and 1.05, rounded to whole units (D35), and the bonus is a share of base for about a third of employees, weighted toward US, GB and DE.
5. History, back-filled. Walking back from that base, each 1 April revision divides out its raise, drawn from `PROMOTION_RANGE` where the level moved and from `RAISE_RANGE` otherwise, each base rounded to 100, down to the joining record. Every revision is kept, chained half-open, a promotion's note `promotion to L<n>`, the others `annual raise` and the first `joining`. Components, bonus and `TAX` are recomputed for each record at its level, and a leaver's last record ends at `last_date + 1`. Everyone employed on 1 April 2020 has a record starting that day: where the record running into it started earlier, which is only a joiner of the six months before it, a revision that day repeats its lines and bonus with the note `Reporting cut-off, FY 2020-21: pay unchanged` (D70). On the seed of 15,000, 479 people have it and 6,987 skipped their first April. No seeded record is cancelled. A long-serving employee's early pay can fall below today's country minimum, a warning the seed accepts.

The employee's `level` and `designation` are those at the last review. `make_import_file --all` writes all 15,000 employees, leavers with their `last_date`, which the import's 15,000-row limit allows, and the import timing reads that file. `--raises N` alone writes N employees still employed on the raise date, passing over the leavers among the earliest joiners.

`seed_data` (`seed/management/commands/seed_data.py`): `--active 10000 --exited 5000 --seed 42 [--reset | --if-empty]` as SPEC section 11. The flow is `ensure_lookups`, `ensure_rates`, the HR Manager (`hr@acme.example`, `SEED_ADMIN_PASSWORD`, required when `DEBUG` is off, `change-me` otherwise), then `bulk_apply` per chunk of 1,000 generated entries with `source="seed"`, `actor=None`, `at=REFERENCE_DATETIME`, inside one `transaction.atomic()` for the whole run. `--if-empty` exits 0 without writing when `Employee` has rows; no flag on a non-empty database is an error; `--reset` first truncates the business tables (`AuditLog`, `CompensationLine`, `CompensationRecord`, `ImportRow`, `ImportBatch`, `Employee`, `ExchangeRate`, `SalaryComponent`, `Department`, `Country`) in dependency order and deletes their `sqlite_sequence` entries so ids restart at 1. `reset_demo` is `--reset` with the fixed counts and seed and keeps users, and `entrypoint.sh` seeds the same counts with `--if-empty`. These two commands are the only code that deletes rows (CLAUDE.md rule 6). Timestamps (`created_at`, `updated_at`, audit `timestamp`) are set to `REFERENCE_DATETIME` by passing `at`, so the determinism scope holds across runs and machines.

Determinism test (`tests/seed/test_seed.py`, marked `slow`): seed 500 active and 250 exited employees with seed 42 into the test database, dump the eight business tables to canonical CSV (tables in a fixed order, rows by primary key, columns in model field order, `Decimal` as text with the field's scale, dates ISO, JSON with `sort_keys=True` and `separators=(",", ":")`), hash with SHA-256 and compare to `tests/seed/golden.txt`. Then run `--reset` on the same database and compare again, which proves the `sqlite_sequence` reset. A change to `profiles.py` is expected to change the hash; the commit that changes it regenerates the file and says so in its body. The same tests assert the shares, the counts on the reference date, the one-open-record invariant, that leavers' records end at `last_date + 1`, that each promotion names the next level up and the last of them the level now, and `--if-empty` behaviour. `tests/seed/test_generator.py` holds the generator to the ladder: every career ends at its level with its experience inside the level's range, the path never falls or skips a level, years at ACME never exceed experience, a leaver stays at least 30 days, every active L1 joined after 1 April 2023, a raise is 3 to 8% and a promotion 12 to 20%, pay follows level and experience up to 20% and reaches the country's minimum, and, marked slow, the full seed's leave rate stays between 10 and 12% every year. Seed timing is recorded by `/perf-timing` on the full run, locally and on Fly. Over 60 s on Fly, the target becomes 120 s, since the seed runs once per volume and the deploy waits up to 10 minutes (D31). `reset_demo` runs on the live machine only on the owner's word, after the machine has been idle, since D65's burst balance sets its speed, and its time is recorded (D64).

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
| `/demo` | `pages/DemoData` | `AppShell` | `useSampleFiles()`, `useResetCounts()`, mutation reset (D72) |
| `/help` | `pages/Help` | `AppShell` | none, the page is static (D75) |
| `*` | `pages/NotFound` | `AppShell` | none |

The pages sit under one pathless route whose `errorElement` is `RouteError`, so a page that fails to render shows the app's own page inside the frame, `This page could not be shown.` with Reload and Go to the dashboard, and never the router's own page with its stack (D76).

Component tree:

```
App
  ThemeProvider (lib/theme) + CssBaseline
  QueryClientProvider
  SessionGate               bootstraps the session once (refresh if a token exists), then renders the router
    RouterProvider
      Login
      RequireAuth -> AppShell (a frame of the window's height and at least 1024 px wide, a narrower window scrolling sideways, D75: `html`, `body` and `#root` are 100% high and the frame 100% of them, which leaves out a sideways scrollbar where 100dvh would count it and add a vertical one. main takes focus from code alone, a place to read from rather than a control, so it draws no focus ring, and every control keeps its own visible focus (SPEC section 13). Left nav: Dashboard, Employees, Imports, then under a divider Demo data and Help. Top bar: user email, Sign out. main is the one scroll container, put back at the top and focused on a route change)
        Dashboard: PageHeader, DashboardFilterBar(CountrySelect, DepartmentSelect, CurrencySelect, Include exited, Clear filters, and at its end the quiet link `Why are some figures hidden?` to `/help#hidden-figures`) in a bar stuck to the top of main as the cards scroll, across main's padding on the page background with a hairline under it, held up by main's padding so it sits flush, where the window is at least 1024 px wide and 600 px tall, so a small or zoomed window keeps its cards in view, and while it sticks main's scroll-padding-top is its height, so a control reached with the keyboard is never under it (D75), RateMonthLabel (the summary's rate month, each pair's rate and date on hover or focus) with the summary's ExportMenu at the right end of the same line, a small `Export` button named and titled `Export summary` (D60), KpiRow(KpiCard x4), a two-column grid of ByCountryCard and ByDepartmentCard (both drawn by CostBars), DistributionCard, ByLevelCard, and GenderGapCard spanning both columns, each InsightCard(question as its heading, an ExportMenu in its `actions` slot, a small `Export` button named and titled for its table, `Export pay by level`, children). Every chart's figures are also a table read by screen readers, every row included, and a withheld figure says why, `fewer than 5 people` or `fewer than 20 people`; a note under the chart names the groups it does not draw. The histogram sits on a number axis, so p10, the median and p90 are drawn at their own values. ByLevelCard draws a median dot on a p25 to p75 bar with p10 to p90 whiskers, and says so, never min or max. With nobody in the filters the KPI row shows 0 and `—` and the empty state replaces the cards; under five people the money KPIs show `—` captioned `Shown for 5 people or more` (D59)
        Employees: PageHeader(actions: ExportMenu as an `Export` button named and titled `Export employees`, Add employee), FilterBar(directory), SearchField, ServerGrid(columns.directory), EmptyState, ErrorState
        NewEmployee: PageHeader, EmployeeForm(identity fields, country select, RecordLinesFields(components for the country), bonus, effective_from, note)
        EmployeeDetail: PageHeader(employee name, code, StatusChip, actions: Edit, Add revision, Mark exited), CurrentRecordCard(gross first, lines in local currency with a monthly column, totals in local and reporting currency, shown label, or a line saying the employee left before pay started (D50)), HistoryList(RecordRow x n, cancelled rows greyed and struck through with "cancelled", Cancel button on scheduled rows after version 1), AuditTab(AuditList), EditIdentityDialog, RevisionDialog, ExitDialog, CancelConfirm
        Imports: PageHeader(TemplateMenu: all countries or one, fetched with the bearer token and saved from a blob), UploadDropzone(drop, or the Choose a file button for one pointer and the keyboard; a file over 10 MB refused before it is sent; a refusal listed in the focusable ErrorSummary), BatchList(file name linking to the review with the ignored columns under it, uploaded, StatusChip, rows, valid, warnings, errors; 25 a page), EmptyState
        ImportReview: back link, PageHeader(file name, StatusChip and who uploaded it when, actions: TemplateMenu, Discard (confirmed in a dialog), Approve (confirmed in a dialog titled `Approve <file name>?` that names the rows it applies, its button `Approve and apply`, a refusal listed in the dialog under `Nothing was applied`; while blocked, disabled with the reason as a tooltip and described by a copy of it with the `hidden` attribute, read only as Approve's description, D75)), BatchSummaryStrip(labelled figures: total, valid, warning, error, skipped, no-op, then one message slot, D75: flex 1 at the figures' height, dropping under them only on a window too narrow for both, one message at a time, the message and `Message 1 of 3` in an `aria-live="polite"` region without the buttons, the place starting again from the first whenever the messages change, the blocker first in its warning tone with a `Show them` link that sets the Status filter to Error, then each batch warning, the ignored columns among them, in info tone, two lines at most with the full text as a native title, and with more than one `1/3`, read out as `Message 1 of 3`, between `Previous message` and `Next message` buttons that wrap around, dots beside them for the eye alone, never rotating on their own), the batch's state (applied counts, the failure's summary, or discarded), StatusFilter and SearchField with their state in the URL, ServerGrid(importRowColumns, in the owner's order of 9 October (D75): the Skip toggle first, as the pencil leads the directory, never hidden, which says in an error notice why a skip did not take, then row, status, the Messages column in text, action, legacy_code, name, then every sheet column as typed, a cell a message is about tinted by severity with the message as its tooltip; rows grow to their messages, so fewer than ten fit the grid's fixed height at once), EmptyState
        Help: PageHeader, How it works (an ordered list of six steps in one outlined card, each step's figure in ink-blue tabular numerals, hidden from screen readers since the list numbers it already), the Demo data link, Questions (twelve Accordions in one outlined card, each with an anchor id, opened, scrolled into view and its question focused when the URL's hash names it, the hash read as it stands so a stray `%` cannot throw, the card keyed on it so a new anchor opens its answer, opening without motion), the steps' list given `role="list"` since Safari drops it once the markers are off (D75)
```

API layer (`src/api/`): `client.ts` exports `apiFetch<T>(path, {method, body, query})` which prefixes `/api/v1`, serialises `query` (arrays joined with commas, `undefined` dropped), sets the bearer header and `Content-Type: application/json` unless the body is `FormData`, parses JSON, and throws `ApiError {status, data}` with a `fieldErrors()` helper. On 401 it awaits `refreshOnce()`, a module-level promise shared by every concurrent caller so only one refresh is in flight, retries the request once, and on a second 401 clears the session and calls the registered `onUnauthenticated` which navigates to `/login?next=<current path>`. `apiDownload(path, {query})` fetches a file the same way and returns its blob with the name from `Content-Disposition`; `imports.ts` saves the template with it, and `exports.ts` saves an export: `exportEmployees(params, file)` sends the directory's list parameters without the page, and `exportInsight(name, params, file)` sends `insightQuery(params)`, the cards' own query, each through `saveFile` in `lib/download.ts` (SPEC F6). `types.ts` holds hand-written types mirroring the serializer and insight shapes; money fields are `string` and only chart adapters call `Number()`. `keys.ts`:

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

Every parameter object is part of the key, so a filter change is a new query. List and insight queries use `placeholderData: keepPreviousData` so a grid keeps its rows while the next page loads and a card keeps its chart while the next filter loads. Meta queries have `staleTime` of five minutes, everything else the default. Invalidation after mutations: create employee invalidates `employees` and `insights`; identity update, revise, cancel and exit invalidate `['employees', id]` (detail, history and audit share the prefix), `['employees', 'list']` and `insights`; skip and unskip invalidate `['imports', id]`; approve invalidates `['imports', id]`, `employees` and `insights`; discard invalidates `['imports', id]` and `['imports', 'list']`.

Session (`src/lib/auth.ts`): the access token lives in a module variable exposed through a tiny `useSyncExternalStore` store; the refresh token lives in `localStorage` under `acme.refresh` (DECISIONS D21). `setSession`, `clearSession`, `getAccessToken`, `bootstrap()` (one refresh on load when a refresh token exists, otherwise unauthenticated). A refresh runs inside `navigator.locks.request('acme-refresh', ...)` and reads the stored token inside the lock, so two tabs never present the same token (the second presentation would revoke every session, D21); where `navigator.locks` is missing (jsdom) the per-tab single-flight promise stands in. A refused refresh clears the session only while `localStorage` still holds the refused token; if another tab has rotated it meanwhile, the newer token is tried once. `Sign out` posts the refresh token to `/auth/logout/`, clears the session and navigates to `/login`.

Grid adapter (`src/components/grid/serverModel.ts`), pure and unit-tested:

```ts
toListParams({ paginationModel, sortModel, filters, search }): ListParams
  // page = paginationModel.page + 1, page_size = pageSize,
  // ordering = sortModel[0] ? (sort === 'desc' ? '-' : '') + sortField[field] : undefined
fromSearchParams(sp: URLSearchParams): GridState     // page, page_size, ordering, search and every filter
toSearchParams(state: GridState): URLSearchParams    // drops defaults and empties so URLs stay short
```

`ServerGrid` wraps `DataGrid` with `paginationMode="server"`, `sortingMode="server"`, `filterMode="server"`, `disableColumnFilter`, `pageSizeOptions={[10, 20, 50]}` with 10 the default (D75), `rowCount` taken from the query's data, which `placeholderData: keepPreviousData` keeps defined during a refetch (an `undefined` count would reset the page), `paginationModel` and `sortModel` controlled from the URL state, `loading`, `density="compact"`, keyboard navigation left at MUI defaults, and the grid's own column chooser enabled through the toolbar, listing only the columns that can be hidden. It stands at one fixed height of ten compact rows whatever the window, `GRID_HEIGHT`, 505 px for the 52 px toolbar, the 39 px header, ten 36 px rows, the 52 px pager and the borders, plus the grid's own sideways scrollbar while its columns scroll (MUI X's `--DataGrid-hasScrollX` times `--DataGrid-scrollbarSize`), so the tenth row is never under it, the owner's choice of 9 October (D75): main scrolls when the page is taller than the window, and the grid scrolls its own rows past ten, so a default page of ten fits it exactly. Its rows read apart: `getRowClassName` marks every second row `odd`, shaded with the page background, the row separators take `ruleStrong`, a step stronger than the divider, and the hover tint is a little stronger than MUI's, while the review's severity tints sit on their cells above the shading. Every sortable column shows a faint up-down icon at rest, the `columnUnsortedIcon` slot with the root styles that hide it until hover overridden, and the sorted column its arrow at full strength. A column that cannot sort shows none (D63). There is no row click. Directory columns: a pencil (`EditLink`, an icon button linking to `/employees/:id`, named and titled `Edit <full name>`, taking focus with its cell so Enter follows it, never hidden or sorted), code (`ACME-<id>`, sorted by id), legacy code, name, email, department, country (the name, since the API orders by name), designation, level, status (chip), record (the shown record's label written out: `current`, `from 1 Jan 2027`, `exited 30 Jun 2026`), gross local, gross reporting (headed `Gross (USD)` or `Gross (EUR)`, and with `currency=local` the one country's code, `Gross (INR)`), joining date, last date, effective from, version. The free grid cannot pin the pencil, since column pinning is a Pro feature in MUI X 9, so the grid shows by default only what fits a 1280 px window without sideways scrolling, the pencil, code, name, department, country, level, status, gross reporting and joining date, and the rest wait in the chooser (D63); the pagination and sort models handed to the grid are memoised on the URL values, because a fresh model each render makes the grid re-apply it and reset the page; money columns are `type: 'number'` with a `valueFormatter` calling `formatMoney`. Name, email, department and designation render through `titledText`, which keeps the cell's ellipsis and puts the full value in a native `title` (D75). Import review columns, in the owner's order of 9 October (D75): the skip toggle first, as the pencil leads the directory, never hidden, then row, status chip, the Messages column, action chip (`No-op` for a row that changes nothing, D76), legacy_code, name, then one column per template column; a cell whose field has a message gets the severity tint and a tooltip with the message text, any other cell its value as a native `title` (D75), and the Messages column after the status lists them.

FilterBar (`src/components/filters/`): `useUrlFilters()` reads and writes `useSearchParams` for the directory's keys and `useDashboardFilters()` for the dashboard's, so filters, page, sort and search survive reloads and are shareable links. The directory keys are `country`, `department`, `designation`, `level`, `status`, `gross_min`, `gross_max`, `joined_after`, `joined_before`, `currency`, `search`, `page`, `page_size`, `ordering`. The dashboard keys are `country`, `department`, `currency`, `include_exited`, and from step 8 each card's control under its prefix: `trend.measure`, `tenure.level`, `mix.view` and `gap.view`, a default value left out of the URL (D62). Clear filters resets the card controls with the bar's filters. On the directory, Clear filters resets the filters and the search, keeps the sort and the page size, and goes back to page 1 (D63). Changing any filter resets `page` to 1. The currency select offers `USD`, `EUR`, and `Local` only while exactly one country is selected; when the country selection changes away from one country and `currency` is `local`, the hook rewrites it to `usd`, and a URL that arrives that way is read the same. The country and department selects hold a choice while their menu is open and commit it when the menu closes, so a switch from one country to another is one change and keeps `local`, in the new country's currency (D59). The designation field is free text, matched exactly but case-insensitively, since titles have no lookup endpoint (D40), its helper reading "Commas between titles, Enter applies" (D76). Every updater builds the next URL from the latest one, held in a ref the hook refreshes on each render and on each write, since React Router 8.4's `setSearchParams` hands its updater the params of the render that made it, and a callback that outlives a render, CommitField's debounce first, would otherwise write a pre-Clear URL back. CommitField drops its draft and its pending timer when its value changes from outside, and the directory's Clear filters drops every draft in the bar, a value it leaves as it was included, so nothing typed before it is sent after it (D76). The UI never sends `on` to the directory or the employee pages: the reporting-date picker is P1 and the API defaults to today. The dashboard's rate label asks `/meta/exchange-rates/` for the rates on its period's `to` (D66).

Formatters (`src/lib/money.ts`, `src/lib/dates.ts`): `formatMoney(value: string, currency: string, { fraction = 0 })` uses `Intl.NumberFormat('en-US', { style: 'currency', currency, currencyDisplay: 'code', minimumFractionDigits, maximumFractionDigits })` and gives `INR 1,450,000`; grids and charts use whole units, detail lines and forms two decimals; `formatCompact` gives `USD 1.2M` for axes; `monthly(value)` divides by 12 for the "per month" line on the detail card; `formatDate` gives `7 Oct 2026` and `formatDateTime` `7 Oct 2026, 14:30` for audit timestamps, built from a fixed list of three-letter months, so September is `Sep` where `en-GB` writes `Sept` (D62), and `formatAxisDate` gives a chart axis `Sep 2026` for a month-end and `7 Oct 2025` for any other day (D69). `formatMoney(value, currency, { signed: true })` writes a change as `+USD 23,000`, `-USD 6,250` or `USD 0`. Codes are always shown with the number, never a symbol, because six currencies sit in one grid.

Forms (`src/components/forms/`): `react-hook-form` with `zodResolver`; `schemas.ts` mirrors the input serializers (`employeeCreateSchema`, `identitySchema`, `revisionSchema`, `exitSchema`), with amounts as strings matching `/^\d+(\.\d{1,2})?$/` so no float arithmetic happens in the browser; `applyServerErrors(error, setError)` maps `{field: [message]}` onto fields (`lines.<code>` onto the line input) and `detail` onto a form-level alert; validation runs on blur and the submit button is never disabled for an invalid form, the error summary is announced instead. The summary takes focus after each failed submit and at no other time, so an error found on blur never pulls focus off the field being edited. A dialog's paper is its form (`formPaper(submit)`), so the content scrolls between a fixed title and actions. Gender and level options come from `lib/constants.ts`, and the gender schema turns the select's string into a `Gender`, so no cast is needed. Changing the country on the new-employee form clears the lines typed for the old one, and a failed countries or departments load shows an error with Retry. `RecordLinesFields` renders one amount input per component of the chosen country from `useComponents(country)`, grouped by kind, BASE marked required, with the computed preview of gross, net and total cost done with `Number()` purely for display and labelled "preview", not announced on every keystroke.

Error and empty states, one sentence that says what to do next:

| Where | Text |
| --- | --- |
| Directory, filters match nothing | "No employees match these filters. Clear a filter or change the search." |
| Directory, no data at all | "No employees yet. Import a spreadsheet or add an employee." |
| Imports, none yet | "No imports yet. Download the template, fill it in and drop it here." |
| Review grid, status filter empty | "No rows with this status. Choose another status." |
| Employee not found | "This employee does not exist. Go back to the directory." |
| Dashboard, empty population | "No one matches these filters today. Clear a filter." (the headcount shows 0, the money figures `—`) |
| Dashboard, nobody on file and no filter set | "No employees yet. Import a spreadsheet on the Imports page, or use the sample files on Demo data.", both named pages linked (D78) |
| Dashboard, a filter the API refuses (400) | the API's own words in one alert under the filter bar, with Clear filters beside it, in place of the cards (D58, D76) |
| Directory, a filter the API refuses (400) | the API's own words under that filter's field, more than 20 titles on Designation, and above the grid for a parameter the bar has no field for (D61, D76) |
| Dashboard, a link whose period cannot be read | the dashboard on Last 12 months, the URL replaced, and the line "This link's period could not be read, so the dashboard shows the last 12 months." (D76) |
| Directory, Gross min above Gross max | "Gross min is above Gross max" under the two fields, the grid as the API answers (D76) |
| Directory, review grid or Imports list, a page past the last | the last page, the URL replaced, no message, the first page's count giving the last (D77) |
| A page that fails to render | "This page could not be shown." under the heading "Something went wrong", with Reload and Go to the dashboard, inside the frame (D76) |
| Any failed load | "Could not load <thing>. Check your connection and try again." with a Retry button that refetches |
| Approve disabled | tooltip "3 rows have errors. Skip them or fix the spreadsheet and upload again." |
| Login failure | "Email or password is wrong." and on 429 "Too many attempts. Wait a minute and try again." |
| Demo data, database empty | the six generated files disabled with "Import the base file first" (D72) |
| Reset dialog, 403 | "password did not match" under the password, "type RESET to confirm" under the confirm field, and on 429 "Too many attempts. Wait an hour and try again." |
| Imports, after a reset | a status alert "The database is empty. Import base-15000.xlsx to start." |
| Upload, approve or reset cut by the proxy | "Still working. The server is reading the file." (or "applying the rows", "emptying the database"), and after ten minutes "The server may still be working, or the file was refused; check the batch list." (approve: "or the approve was refused; open the batch again", reset: "or the reset was refused; reload the page and check the counts") |

A 400 maps onto fields, a 409 shows the server's `detail` in an inline alert beside the action that caused it, a 401 goes through the refresh path, anything else shows the failed-load state. No 4xx is retried, since the answer would not change, and a lost connection or a 5xx is retried once (D76).

Step 9 (D64). The dashboard bar gains `PeriodControl` before Clear filters: a small `Select` of Last 3 months, Last 6 months, Last 12 months (the default), Current FY to date, Last FY and Custom, with From and To fields beside it when Custom is chosen (`TextField type="date"`, no new dependency). `src/lib/period.ts` turns a preset into `{from, to}` against today in UTC: Last N months from the day after the same day N months back, or after that month's last day where the day does not exist (12 months ending 8 October 2026 start on 9 October 2025, 6 ending 31 October on 1 May, D69), Current FY to date from the 1 April that opened today's financial year, Last FY the 1 April to 31 March before that. `FY_START = {month: 4, day: 1}` lives in `lib/constants.ts`, the one place the financial year is defined. The URL keeps the preset's name under `period` (`last_3_months`, `last_6_months`, `fy_to_date`, `last_fy`, `custom`), the default left out, and `custom` keeps `from` and `to`, so a shared link stays relative. A custom range outside 1 April 2020, the reporting cut-off, to 31 December 2100 (D70), or with From after To, says so under the fields and keeps the last valid period. Every insight query and export sends `from` and `to`, and both are in every query key. Clear filters resets the period to Last 12 months with the rest. When `to` is not today, ByLevelCard, ByTenureCard and GenderGapCard's By level view carry the caption `Levels are as of today; anyone promoted after <to> appears at their new level`.

The upload box reads `Drop a .xlsx or .csv here, or choose a file. Up to 15,000 rows and 10 MB.` (D64).

The KPI row has five cards: Headcount, Annual cost, Mean gross and Median gross, each `on <to>`, and Spent in period, captioned with its dates. `InsightCard` takes an `on` prop and shows `On 7 Oct 2026` under its question on every card that shows a state, and trend and the bridge show `From 8 Oct 2025 to 7 Oct 2026`. The trend's axis names a month-end `Sep 2026` and a first or last day that is not one `7 Oct 2025`, the year in full (D69). `RateMonthLabel` says the one rate covers the whole period.

The directory's Status filter defaults to Active. The URL leaves Active out and writes `status=any` for Any, and Clear filters goes back to Active. With D63's order, a request without `status` gets what the grid shows.

`ServerGrid` replaces the pager's previous and next with `PageNumbers`, the grid's `pagination` slot kept as `GridPagination` for Rows per page and `1–10 of 10,000`, its actions MUI's `Pagination` (`boundaryCount={1}`, `siblingCount={1}`, ellipses) and a `Go to page` number field that jumps on Enter and clamps to the pages there are. The page stays in the URL. The import review grid gets the same through `ServerGrid`.

Step 10 (D72). The nav gains `Demo data` after Imports, route `/demo`, `pages/DemoData` with `useSampleFiles()` (`GET /admin/sample-files/`), `downloadSampleFile(name)` through `apiDownload` and `saveFile`, `useResetCounts()` (`GET /admin/reset-demo/`, fetched when the dialog opens) and `useResetDemo()` (the POST). The page opens with one line, `The demo runs on a small shared machine, and a large import can take a few minutes.` Section A, `Sample files`, lists the seven files, each with its file name, one line saying what it exercises and a Download button; while `employees` is 0 the six generated ones are disabled, with `Import the base file first` as their helper text. The lines: base-15000 `The whole organisation, 10,000 on staff and 5,000 who left, as the seed built it. Into an empty database it creates everyone; into the seeded one every row is a no-op, the scale test.`, newhires `500 new employees with fresh legacy codes who joined between 60 days ago and 14 days ahead, the future ones shown as Upcoming until they join. Each row creates an employee.`, diwali-bonus `1,000 employees with 5 to 15% of base added to their bonus, effective today. Each row is a revision.`, april-raises `1,000 employees with base up 3 to 8%, components with it, effective 1 April next. Each row is a scheduled revision.`, promotions `200 employees one level up with the designation to match and base up 12 to 20%, effective today. Each row changes identity and amounts at once.`, exits `100 employees with their last day between 14 days ago and 60 days ahead: the past ones leave the counts at once, the future ones are scheduled exits and stay active until the day. Each row is an exit.`, fix-me `50 rows, 30 raises and 20 new joiners, with 6 planted errors to skip or fix in the sheet.` Under the list, two notes: `After a base import every employee has one record dated at joining, so the trend and the bridge show joins and exits but no pay changes until revision files are imported, and Spent in period reads high, today's pay counted back to joining.` and `A revision file imported into an empty database creates its employees instead, and the base file then shows those rows as errors. Empty the database and start with the base.` Section B, `Danger zone`, at the bottom in the error colour's outline, holds `Empty the database`, which opens `ResetDialog`: what will be deleted as the live counts (`15,000 employees, 51,659 compensation records, 128,000 lines, 3 import batches with 150 rows, 70,000 audit entries`), a password field, a `Type RESET to confirm` field, and the button off until the box holds exactly `RESET`, case-sensitive with no surrounding spaces, and the password field something (the server still checks both). Once pressed, the busy dialog of section 6 takes over on top of the form, so nothing on it can be touched meanwhile; a 403 shows there with Close and then on the two fields. On success every query is cleared and the page navigates to `/imports` with `{ reset: counts }` in the router state, which Imports shows as a status alert while the list is empty.

Long requests behind one dialog (D72, the owner's patch of 9 October). Every request the server finishes on its own, or that can run long, runs behind the dialog of `components/busy/BusyProvider`, mounted once at the app root: upload (staging), approve, discard, reset, each directory and insight export, and each sample-file download. `useBusy().run(title, task, options)` opens the modal with the action's words as its title (`Staging acme-sample-50.xlsx…`, `Applying 1,000 rows…`, `Discarding october.csv…`, `Emptying the database…`, `Preparing employees.csv…`), a spinner and the seconds elapsed, and after 20 s `The demo runs on a small shared machine; this can take a few minutes.` While the request is pending it cannot be dismissed: no button, Escape and the backdrop do nothing (MUI 9 has no `disableEscapeKeyDown`, so `onClose` checks the reason), the modal covers the navigation and traps focus, and a `beforeunload` listener makes the browser warn that the action is still running. Buttons that start these actions are off while it is open (`useBusy().busy !== null`), so no second upload, approve or export can start. On the result it closes and the page updates: the review page, the batch list, Imports after a reset, the saved file. On a network error, a 502 or a 504, which is how a cut request reaches the page, it says `Still working…` and polls through `lib/poll.ts`'s `waitFor(check, { every: 5000, upTo: 600000 })` with the action's `recover`: the batch list for a batch newer than the newest before the upload with the file's name, the batch until it leaves `review`, the counts until every one is 0; after ten minutes it turns into a plain dialog with the message D72 names (where to look: the batch list, the batch, or the counts) and a Close button. On an error response it shows the refusal in place under the action's failed title (`The file was not staged`, `Nothing was applied`, `Not discarded`, `The database was not emptied`, `Could not export the summary`, `Could not download exits.xlsx`) with a Close button, the only time it can be dismissed. A download has nothing to look for, so a cut connection is a failure there. Fly's proxy closes a connection that carries no data for 60 s, and a gthread worker learns of it only when it writes the response, so the work completes on the server whichever way the page learns of it.

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
| `ruleStrong` | `#C9CEC4` | the grids' row separators, a step stronger than `rule` so rows read apart, 1.6:1 on white against `rule`'s 1.3:1 (D75) |
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
| `chart.marker` | `#646C78` | p10, p50 and p90 reference lines, the employer contribution in the cost mix |
| `mix` | ochre `#A0790A`, teal `#00897B`, plum `#7B4FA0`, navy `#283593`, purple `#8E44AD`, brown `#8D6E63`, other `#7D8590` | the cost mix's own components beside the two series: HRA, allowances, holiday allowance and AWS, then National Insurance, social insurance and CPF. No two segments of a view share a swatch, each clears 3:1 on white, and each stands apart from its neighbours in a bar under deutan, protan and tritan vision (D62) |
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
│ Imports  ││ October 2026 rates                                       [Export ▾] │
│          ││ ┌ Headcount ┐ ┌ Total cost   ┐ ┌ Mean gross ┐ ┌ Median gross ┐      │
│          ││ │ 9,214     │ │ USD 1.02B    │ │ USD 110,400│ │ USD 96,250   │      │
│          ││ │ 6 countr. │ │ 12 departm.  │ │            │ │              │      │
│          ││ └───────────┘ └──────────────┘ └────────────┘ └──────────────┘      │
│          ││ ┌ Where does payroll go, by country?  ▾┐ ┌ Which departments cost most? ▾┐│
│          ││ │ IN ▇▇▇▇▇▇▇▇▇ 41%   US ▇▇▇▇▇ 27% ...  │ │ Engineering ▇▇▇▇▇▇▇▇ USD 310M  ││
│          ││ └──────────────────────────────────────┘ │ Sales       ▇▇▇▇ USD 140M      ││
│          ││ ┌ How are salaries distributed?       ▾┐ └────────────────────────────────┘│
│          ││ │ ▁▃▅▇▇▅▃▂▁▁▁▁   p10 ┊  p50 ┊  p90 ┊    │ ┌ What does each level pay?   ▾┐ │
│          ││ └──────────────────────────────────────┘ │ L1 ├─•─┤  L2 ├──•──┤ ...        │ │
│          ││ ┌ Is there a gender pay gap?          ▾┐ └────────────────────────────────┘ │
│          ││ │ IN ▇▇ ▇▇ 3.1%  US ▇▇ ▇▇ 1.8% ... Overall ▇▇ ▇▇ 2.4%   ■ female ■ male  │ │
└──────────┘└─────────────────────────────────────────────────────────────────────┘
```

`▾` on a card's title line is that card's Export button, the same menu of CSV, Excel and JSON as `[Export ▾]` (D60).

Step 8 (D62) groups the dashboard's cards under three headings, in this order. What we spend: the KPI row with its rate month line, TrendCard across both columns, CostBridgeCard beside ByCountryCard, ByDepartmentCard beside CostMixCard. How pay is structured: DistributionCard across both columns, ByLevelCard beside ByTenureCard. Is pay fair: GenderGapCard across both columns. A card's control, `CardControl`, sits in its header before the Export button: a small exclusive `ToggleButtonGroup` named for the card for two to four choices (Total cost or Headcount, Cost or Take-home, Pay gap, Bonus, Quartiles or By level), and a small `Select` for the Level (All, 1 to 6). Its value is part of the card's query key, so a switch refetches that card alone, and the card's Export button sends it.

Step 9 (D64): the bar reads `[Country ▾] [Department ▾] [Currency ▾] [☐ Include exited] [Period: Last 12 months ▾] Clear filters`, Custom adding `[From] [To]`. The KPI row is five cards, Spent in period last. Each state card carries `On 7 Oct 2026` under its question. The grid footer reads `Rows per page [10 ▾]   1–10 of 10,000   ‹ 1 … 4 5 6 … 1000 ›   Go to page [   ]`.
- TrendCard and CostBridgeCard, while Include exited is ticked, carry the caption `Counts people employed on each date; Include exited doesn't apply`.
- TrendCard: one line for the chosen measure, never two axes, subtitled `month-end totals, latest 30 Sep 2026` and `at October 2026 rates`. A withheld point is a gap in the line, and the hidden table says why.
- CostBridgeCard: a waterfall of five floating bars (Recharts `Bar` with `[low, high]` values), start and end from zero, leavers down, joiners and pay changes up, a withheld part showing its people and the reason.
- ByTenureCard: one bar per band, median gross, with the band's headcount under its label, so a band withheld for want of people still says how many it has.
- CostMixCard: one bar per country stacked to 100%, segments in the one order the API gives, each component its own swatch from the `mix` tokens, with a legend since there are several series. A withheld country is named under the chart with its reason.
- GenderGapCard: titled `Is there a gender pay gap? (on annual pay)`, with the note `Follows EU Directive 2023/970 Article 9 and the UK's six gender pay gap measures, on annual pay. Not a statutory filing: no hours, no legal entities.` Pay gap as today. Bonus: grouped bars of the share receiving a bonus, the mean and median gaps as a two-line label above each pair, and a tooltip with both shares and gaps. Quartiles: four bars of women's and men's shares, with other and undisclosed counted beside, never ranked. By level: per country a grid of levels with both gaps, a flagged one marked `5% or more, the threshold in EU Directive 2023/970 Article 10`, and other and undisclosed counted per country under it. Other and undisclosed are counted beside each view, and a group with nobody shows `—`.

Directory:

```
┌ nav ─────┐┌─────────────────────────────────────────────────────────────────────┐
│          ││ Employees                      [Export ▾] [+ Add employee]           │
│          ││ [Search name, code or email        ] [Country ▾] [Department ▾]      │
│          ││ [Designation ▾] [Level ▾] [Status ▾] [Gross USD min] [max] [Joined..]│
│          ││ ┌───┬─────────┬────────────┬──────────────┬───────────┬─────┬────────┬───────────────┬────────────┐
│          ││ │   │ Code ↑  │ Name ↕     │ Department ↕ │ Country ↕ │ L ↕ │ Status │ Gross (USD) ↕ │ Joined ↕   │
│          ││ │ ✎ │ ACME-17 │ Asha Rao   │ Engineering  │ India     │ 3   │ active │ USD 17,400    │ 3 Mar 2021 │
│          ││ │ ✎ │ ACME-18 │ Ben Carter │ Sales        │ US        │ 2   │ exited │ USD 98,000    │ 9 Jun 2019 │
│          ││ │ …  ✎ opens the employee. A sortable header shows ↕, the sorted one its arrow                    │
│          ││ └─────────────────────────────────────────────────────────────────────────────────────────────────┘
│          ││                          Rows per page [10 ▾]   1–10 of 10,000   ‹ ›  [Columns]   │
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
│          ││ Asha Rao  ACME-17  [active]         [Edit] [Add revision] [Mark exited]│
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
│          ││ │   Drop a .xlsx or .csv here, or choose a file.                  │ │
│          ││ │   Up to 15,000 rows and 10 MB.                                  │ │
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
│          ││ [3 rows have errors. Skip them or fix…  Show them  ‹ 1/2 › ● ○]     │
│          ││ Status [All ▾]  [Search code or name     ]      (Approve tooltip:   │
│          ││                                                  3 rows have errors) │
│          ││ ┌────┬───┬─────────┬──────────────────────────┬────────┬─────────┬──┐│
│          ││ │Skip│ # │ Status  │ Messages                 │ Action │ Name    │ …││
│          ││ │skip│ 12│ [error] │ BASE must be a           │ revise │ R. Iyer │ …││
│          ││ │    │   │         │ non-negative number, got │        │         │  ││
│          ││ │    │   │         │ -5000                    │        │         │  ││
│          ││ │skip│ 13│[warning]│ gross below minimum      │ revise │ M. Khan │ …││
│          ││ │skip│ 14│ [valid] │ No changes, row will be  │ noop   │ ...     │ …││
│          ││ │    │   │         │ skipped                  │        │         │  ││
│          ││ └────┴───┴─────────┴──────────────────────────┴────────┴─────────┴──┘│
│          ││                                   Rows per page [10 ▾]  1–10 of 50   │
└──────────┘└─────────────────────────────────────────────────────────────────────┘
```

Step 10 (D72), the Demo data page:

```
┌──────────┐┌─────────────────────────────────────────────────────────────────────┐
│ Dashboard││ Demo data                                                           │
│ Employees││ The demo runs on a small shared machine, and a large import can     │
│ Imports  ││ take a few minutes.                                                 │
│ ──────── ││                                                                     │
│ Demo data││ Sample files                                                        │
│ Help     ││ base-15000.xlsx   The whole organisation, 10,000 on staff... [Download]│
│          ││ newhires.xlsx     500 new employees who joined in the...   [Download]│
│          ││ diwali-bonus.xlsx 1,000 employees with 5 to 15% of base... [Download]│
│          ││ april-raises.xlsx 1,000 employees with base up 3 to 8%...  [Download]│
│          ││ promotions.xlsx   200 employees one level up...            [Download]│
│          ││ exits.xlsx        100 employees with their last day today. [Download]│
│          ││ fix-me.xlsx       50 rows with 6 planted errors...         [Download]│
│          ││ (empty database: the six generated rows read "Import the base file   │
│          ││  first" and their buttons are disabled)                              │
│          ││ After a base import every employee has one record dated at joining...│
│          ││ A revision file imported into an empty database creates its...       │
│          ││                                                                     │
│          ││ ┌ Danger zone ──────────────────────────────────────────────────┐   │
│          ││ │ Empty the database. Lookups, rates and your login stay.        │   │
│          ││ │                                        [Empty the database]    │   │
│          ││ └───────────────────────────────────────────────────────────────┘   │
└──────────┘└─────────────────────────────────────────────────────────────────────┘

Dialog: "Empty the database?"  This deletes 15,000 employees, 51,659 compensation
records, 128,000 lines, 3 import batches with 150 rows and 70,000 audit entries.
[Your password          ] [Type RESET to confirm   ]        [Cancel] [Empty the database]
```

## 9. Testing

Backend layout: `backend/tests/conftest.py`, `tests/factories.py`, then `tests/<app>/test_<unit>.py` mirroring `apps/`. Settings `acme_salary.settings.test` with in-memory SQLite, `PASSWORD_HASHERS = [MD5PasswordHasher]` for speed, the login throttle kept so the 429 test is real.

Fixtures (`conftest.py`): `lookups` (calls `ensure_lookups`), `rates` (calls `ensure_rates`, sixteen rows), `today` (`freeze_time("2026-10-07")`, applied to every test through `autouse`), `hr_user` (`UserFactory`), `api` (`APIClient` with a bearer token for `hr_user`), `anon` (bare `APIClient`), `clear_throttle_cache` (autouse, `cache.clear()`).

Factories (`factory_boy`): `UserFactory`, `EmployeeFactory` (created in the app, so numbered by the database with no `legacy_code` unless a test passes one, `country` and `department` taken from the lookups, `joining_date = 2020-01-01`), `CompensationRecordFactory` (`version` from a per-employee sequence, `effective_from = joining_date`, `currency_code` from the country, totals computed by the service in a `post_generation` hook from a `lines` mapping, default `{"BASE": 100000}` plus the country's required lines at zero), `ExchangeRateFactory`, `ImportBatchFactory`, `ImportRowFactory`, `AuditLogFactory`. Factories create the minimum rows and never call the 10k seed.

Service tests per app (SPEC section 12 table, one file per unit): `tests/compensation/test_totals.py`, `test_services.py` (next-day revision, scheduled revision, cancel and re-chain, exit closing, the one-open-record invariant through the constraint, version assignment, the 409 and 400 cases), `test_bulk_apply.py` (equality with the single path, chunking at 1,001 entries), `test_validators.py` (every section 7 rule with one passing and one failing case, asserting field, severity and the full message); `tests/core/test_fx.py` (rate by date, the earliest-rate fallback, routing through USD, the inverse-leg fallback, `convert` precision, `case_expression` SQL against a small directory) and `test_set_exchange_rate.py`; `tests/employees/test_services.py` and `test_queries.py` (`pick_shown` against the subquery, the annotation on a fixture with current, scheduled, exited and cancelled rows, `gross_bound`); `tests/imports/test_parser.py` (header aliases, `1,200`, `12,00,000`, `1.200.000,50`, Excel dates, the 15,001st row (D64), every upload limit of D56, refused before openpyxl opens the file, and the first worksheet read alone with no external link followed, D57), `test_template.py`, `test_staging.py` (the decision table row by row, counts unchanged on live tables, blank and long cells), `test_applier.py` (skip, unskip, discard and their 409s, then approve over a fixture that includes a promotion row changing identity and amounts and an exit-with-raise row, with the audit count `2 x created + updated + revised + (revised rows that also changed identity or set last_date) + (exit rows whose only record had not started, D50) + 1`, the simulated failure through a monkeypatched `bulk_record` raising after the closing and identity updates, re-validation after a UI revision), `test_api.py` (the same over HTTP, with query counts), `test_make_import_file.py`; `tests/audit/test_snapshots.py` and `test_record.py`; `tests/exports/test_writers.py` (escaping in CSV and XLSX and none in JSON, the BOM, a hundred rows a chunk, typed XLSX cells, a control character replaced) and `test_api.py` (over DESIGN 9's fixture: a filtered export holds exactly the rows the list pages through, in each format; the seventeen columns of one employee; `=` escaped in CSV and XLSX; JSON's filters as applied; each insight's table with its Reason, Currency and Rates; a level under twenty and a distribution without bands as headcounts, a level of twenty with p10 to p90 (D59, D60); every insight table ending with Reason, Currency and Rates; `on` applied; a missing rate and a failing row answered before the CSV's 200; the 400s, the designation cap (D61) and the 404; query counts); `tests/seed/test_seed.py` (slow).

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
- `by-country`: US headcount 10, total cost 1,595,000.00, median 145,000.00, share 65.5; IN 12, 319,200.00, 23,750.00 (median of 12 values, the mean of 1.8M and 2.0M INR), 13.1; then, each showing its headcount alone (D59) and in name order, DE 4, NL 0, SG 0 and GB 1.
- `by-department`: Engineering headcount 15 (U1 to U5, I1 to I6, D1 to D4), total cost 1,219,200.00 (660,000 + 109,200 + 450,000), mean 71,500.00 (1,072,500 / 15), median 87,500.00 (the 8th of 15); Legal headcount 0 with nulls; Finance headcount 1, its headcount alone (D59).
- `distribution`, no filter: 27 values; p1 10,650.00, p99 187,400.00 (inclusive method), band width 14,729.17 (176,750 / 12, unquantised), counts `[7,5,0,1,1,1,4,1,2,1,2,2]`, markers p10 16,500.00, p50 75,000.00, p90 164,000.00. With `country=US` the ten people show their headcount alone (D59).
- `gender-gap` row IN: female median 25,000.00 (2.0M INR), male median 22,500.00 (1.8M INR), `gap_pct` -11.1; row US: female headcount 4 so `gap_pct null`, reason `fewer than 5 women` (`group too small` until step 8); overall row computed over all 27.
- `by-level`: no level reaches twenty people, level 3's five included, so every filter asserts the headcounts alone, unfiltered `[4,6,5,5,4,3]` and `country=US` `[2,2,2,2,1,1]` (D59). A fixture of its own puts twenty Dutch salaries at level 1 (50,000 to 97,500 USD in steps of 2,500) and nineteen at level 2: level 1 shows p10 54,750.00, p25 61,875.00, median 73,750.00, p75 85,625.00 and p90 92,750.00 (inclusive method), level 2 its headcount alone.

One test per filter per insight, plus the API test with the pinned query count and the 404 for an unknown name.

Step 8 (D62): `tests/insights/history.py` is a fixture of its own for `trend` and `cost-bridge`, a few employees in two currencies with joins, exits and raises at chosen dates over two years, every expected figure worked out by hand and written as a literal. It covers the bridge's five parts adding up exactly, pay changes summed directly within 3 cents per currency of the balancing figure, 3 leavers withholding leavers, joiners and pay changes while start and end stay, 0 leavers showing every amount, an exited employee counted on neither date whatever Include exited says, and the caption when it is ticked, trend's 24 month-ends for 7 Oct 2026 and for a month-end `on`, one rate for every date, and a point under five people. by-tenure is tested on each band's boundary (exactly 1, 3, 5 and 10 years) and within a level. cost-mix and the gender views read DESIGN 9's fixture, its lines and bonuses known by construction: both cost-mix views, the Bonus shares and gaps, Quartiles with tied pay and a count not divisible by four, By level's mean and median gaps and the 5% flag either way, and `fewer than 5 women`, `fewer than 5 men` and both. For each control, a value outside its list is a 400, the URL keeps it, the export sends it and Clear filters resets it. The step 8 review added boundary pairs at four and five (a bridge with four and with five leavers, a start or an end under five, two short changes at once, tenure level 1's four beside level 3's five, a cost-mix country of four beside one of five, a bonus held by four and then five, quartiles of 19 and 20 women and men and of four and five women, and a bonus gap with four and five women receiving one), a by-level gap of exactly 5.0% and one of 4.999% shown as 5.0 and unflagged, a quartile tie whose man was hired first, mean and median gaps apart, the dates the bridge counts on (a last day before the start, a last day on it and a joiner on `on`), 29 February anniversaries, trend and the bridge under the country and department filters, each view's export as literal rows, the applied control in the JSON filters, and on the dashboard the four controls cleared together, kept through a filter change, each refetching its own card alone and sent by its card's export.

Step 9 (D64): the seed's invariants on `--active 500 --exited 250` (section 5 above) and its golden hash. The directory and its export on Active without `status`, `status=any` for everyone, Clear filters back to Active. `parse_period`'s defaults, bounds and order as 400s. trend's points on a hand-made history: `from`, each month-end and `to`, a month-end `from` or `to` not repeated, and the bridge's start and end equal to trend's first and last points. Spent in period hand-computed across 29 February and a raise mid-period, withheld under five. One rate on every date. Every insight export sending the period, its JSON naming `from` and `to`. The import's row limit at the 15,001st row, and the 15,000-row `--all` file, leavers included, staging cleanly. Frontend: `period.test.ts` for each preset (31 October to 30 April, 31 March to the end of February in a leap year and in another, the financial year on 31 March and on 1 April, Last FY, and from D69 each Last N months starting the day after that date), the levels caption on the three cards when `to` is not today and its absence when it is, the URL keeping a preset's name and a custom range's dates, Clear filters back to Last 12 months, a bad custom range kept from the API, the `On <to>` lines and the Spent in period card, and `PageNumbers` (first, last, neighbours and ellipses, Go to page clamped, rows per page and the page in the URL) on the directory and the import review.

Step 10 (D72): `tests/compensation/test_validators.py` holds the gross warning a cent either side of equality and the no-op on a repeated scheduled revision; `tests/imports/test_staging.py` the cap at exactly 25,000 and refused at 25,001 with no batch, updates and revisions not counted; `tests/imports/test_make_import_file.py` each new option's row shape, share and determinism, newhires' window from the day after, promotions skipping L6, exits passing over a scheduled revision, a raise built on one, two files of one stream sharing no code or email, and a generated file imported twice as no-ops; `tests/demo/test_services.py` the six files made from one database sharing no code or email, each in its share, and importing in page order with no error rows but fix-me's planted ones, then again as no-ops; `tests/imports/test_applier.py` a locked approve as a 409 with the batch still in review; `tests/seed/test_base_file.py` (slow) the committed base file against `ordered_entries(10000, 42, exited=5000)` row by row, and the base file into an empty database creating its leavers exited; `tests/demo/test_services.py` and `test_api.py` the 403s, the 429 on the sixth attempt, the 409 under the import lock, the counts, every pay table empty with `sqlite_sequence` cleared, lookups, rates and the user kept, the user's login afterwards, the one `demo_reset` entry, the file list on an empty and a seeded database, and each download's name and header row. Frontend: the page's seven rows and their lines, the disabled state, the dialog's counts, its button off for `reset`, `RESET ` and `RESE` and on for `RESET` beside a password, the 403 messages in the busy dialog and then on the fields, the navigation to Imports with its alert, and `waitFor` polling after a network error on the review page, the Imports page and the dialog. `components/busy/BusyProvider.test.tsx` holds the dialog itself under fake timers: the seconds, the 20 s line, the `beforeunload` prompt, Escape and the backdrop ignored while pending, the ten-minute fallback, a refusal with Close and a result the caller calls a refusal. Each action's page test holds the request and checks that the dialog opens on send, ignores Escape and the backdrop while pending, closes on the result, and shows the refusal with Close on a failure (`test/busy.ts`).

Frontend: Vitest with `environment: 'jsdom'`, `src/test/setup.ts` starts `setupServer(...handlers)` from `msw/node` with `onUnhandledFrame: 'error'` (MSW 3 renamed `onUnhandledRequest`), resets handlers after each test; handlers in `src/test/handlers.ts` use `http` and `HttpResponse` from `msw/http` (SPEC section 1); fixtures in `src/test/fixtures/` carry four employees (IN active, US active, GB exited, DE with a scheduled revision), one batch with five rows (valid, warning, error, skipped, no-op), and insight payloads in the shapes of section 1.6 with small numbers; `src/test/render.tsx` wraps a component in `QueryClientProvider` (retries off) and a `MemoryRouter`. Tests query by role and label. Unit tests: `serverModel.test.ts` (zero-based page mapping, ordering prefix, URL round trip), `money.test.ts`, `dates.test.ts`, `client.test.ts` (one refresh for two concurrent 401s, redirect after the second), `useUrlFilters.test.ts` (`include_exited`, the local-currency rule). Component tests: `Login.test.tsx` (redirect to `next`), `Employees.test.tsx` (renders fixture rows, a filter change calls the API with the right params, error state), `EmployeeDetail.test.tsx` (history with the cancelled row greyed, cancel on the scheduled row only), `EmployeeForm.test.tsx` (zod message, server field error mapped), `ImportReview.test.tsx` (status filter, approve disabled with the reason), `Dashboard.test.tsx` (each card shows the fixture numbers, a filter change refetches, the include-exited box changes headcount), `InsightCards.test.tsx` (one test per card, read from its table), `ExportMenu.test.tsx` (the three formats, the button's text and tooltip, the spinner and a second click ignored, the failure notice, and on the pages: the directory exports every page with its filters, search and sort, a card and the summary with the dashboard's filters, the files named by the server). jsdom has no ResizeObserver, so `setup.ts` stubs one and the charts stay unmeasured in tests.

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
COPY backend/manage.py ./                          # the runtime alone: no tests, no .env.example (D73)
COPY backend/acme_salary ./acme_salary
COPY backend/apps ./apps
COPY backend/seed ./seed
COPY --from=web /web/dist /app/spa
RUN .venv/bin/python -m whitenoise.compress /app/spa   # gzip and brotli beside each asset
COPY sample-data/base-15000.xlsx /app/sample-data/   # the Demo data page's base file (D72)
COPY entrypoint.sh /app/entrypoint.sh
RUN useradd --system --uid 1000 --user-group acme    # the app's user; the entrypoint starts as
                                                     # root only to chown the volume, then
                                                     # re-executes itself through setpriv (D73)
ENV PATH=/app/.venv/bin:$PATH DJANGO_SETTINGS_MODULE=acme_salary.settings.prod SPA_DIR=/app/spa
EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
```

`entrypoint.sh`:

```
set -euo pipefail
python manage.py migrate --noinput
python manage.py flushexpiredtokens
python manage.py seed_data --active 10000 --exited 5000 --seed 42 --if-empty
exec gunicorn acme_salary.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 8 --timeout 600 --no-control-socket
```

Long requests (D72): Fly's proxy closes a connection that carries no data for 60 s, which no setting of the app changes, so a staging or an approve throttled past that is cut while the worker finishes it, and the pages poll for the result (section 6). gunicorn's `--timeout` is 600 s from step 10. The step checked locally that a gthread worker lets a request longer than its timeout finish: gunicorn 26.2.0 with `--timeout 5` against a view that sleeps 10 s answered 200 after 10.0 s with no worker kill, the timeout being the worker's heartbeat, which the gthread loop keeps alive while its threads work. So the server finishes the work whichever rule applies, and the pages' polling (section 6) is what a reviewer sees.

Step 1 confirms the image's SQLite with `docker run --rm <image> python -c "import sqlite3; print(sqlite3.sqlite_version)"` against Django 6.1's 3.37 minimum and records it in the step's DECISIONS entry.

Environment variables (`.env.example` is committed with placeholders; `.env` never is):

| Variable | Dev default | Production |
| --- | --- | --- |
| `SECRET_KEY` | a dev-only value in `dev.py` | `fly secrets` |
| `DEBUG` | `1` | `0` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | `acme.nutanprabhat.dev` only, so `acme-salary.fly.dev` answers 400 and the site has one name |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | `https://acme.nutanprabhat.dev` |
| `CSRF_TRUSTED_ORIGINS` | same | `https://acme.nutanprabhat.dev` |
| `DATABASE_PATH` | `backend/db.sqlite3` | `/data/db.sqlite3`, absolute, required (D73) |
| `NUM_PROXIES` | `0` | `1` on Fly, `0` in compose (D73) |
| `SEED_ADMIN_PASSWORD` | `change-me` | `fly secrets`, required |
| `SPA_DIR` | unset (Vite dev server) | `/app/spa` |
| `SAMPLE_DATA_DIR` | unset, the repository's `sample-data/` | `/app/sample-data` (D72) |
| `PORT` | `8000` | `8000` from `fly.toml` |

Volume: `fly.toml` mounts volume `data` at `/data`; the database, its WAL and shm files live there. `docker-compose.yml` publishes port 8000 on 127.0.0.1 only, sets `NUM_PROXIES=0` since nothing proxies the app there (D73), and mounts a named volume `acme-data:/data`, with the same environment names read from `.env`.

Fly setup, done by the owner on 7 October before step 1 (D29, D30): the volume `data` in `sin`, the secrets above, `fly certs add acme.nutanprabhat.dev` (issued and verified on IPv4 and IPv6), and a Cloudflare CNAME `acme` to `acme-salary.fly.dev` with the proxy off. The step 1 deploy could not place a 1 GB machine on that volume's host, so a second empty volume named `data` was created in `sin`, the machine runs on it, and the first, never-attached volume was destroyed, leaving one machine and one volume (D31). `fly deploy --remote-only` builds on Fly's builder, and the ask rule prompts for it at the close of every step that adds a page. `.dev` is HSTS-preloaded, so the site is reachable only over the issued certificate. The health check in `fly.toml` hits `/healthz` every 30 s and sends `Host: acme.nutanprabhat.dev` through `[http_service.checks.headers]`, because Fly's checker otherwise sends the machine's internal address as `Host` and `ALLOWED_HOSTS` answers 400 (D29). Fly caps an HTTP service check grace at 60 s and `fly.toml` says `grace_period = '60s'` (D31). A failed check does not restart the machine, it only stops routing and makes `fly deploy` wait, so the seeded first boot, once per volume, runs with `fly deploy --remote-only --wait-timeout 10m` and its measured boot goes into `docs/PERFORMANCE.md`; later boots skip the seed and were healthy 6 s after init.

CI (`.github/workflows/ci.yml`), every action pinned by commit SHA with the tag beside it and every checkout with `persist-credentials: false` (D73): `backend` job (`setup-python` 3.14, `astral-sh/setup-uv`, `uv sync`, `ruff format --check`, `ruff check`, `pytest -q`, then `uv export --frozen --no-dev --no-hashes` and `uvx pip-audit --strict` on it, so any known vulnerability in a locked runtime dependency fails the build), `frontend` job (`setup-node` with `node-version-file: frontend/.nvmrc` and `cache: npm`, `npm ci`, `npm audit --omit=dev`, which fails the same way, `npm run lint`, `npm test -- --run`, `npm run build`), `docker` job after both (`docker build .`). `npm install` never runs in CI. Both audits were clean on 8 October.

## Questions for the owner

Step 10 (D72) assumed these defaults. The owner approved them on 8 October with changes: 1 stands, with gunicorn's timeout raised to 600 s, a local check that a gthread worker lets a request longer than its timeout finish, the three pages treating a network error, a 502 or a 504 on upload, approve or reset as still running, and after ten minutes without a result the upload path saying `The server may still be working, or the file was refused; check the batch list` and the other two the equivalent; 5 re-checks the cap at approve, the employees in the database plus the batch's non-error create rows, a 409 with the same wording, so two batches in review cannot pass it together; 6 answers a reset that waits out SQLite's 20 s lock with 409 `an import is being applied; try again in a moment`, with a test. 2, 3, 4, 7, 8, 9, 10, 11, 12 and 13 stand.

1. Fly's proxy closes a connection with no data for 60 s (Fly staff on its forum; a support request on a higher plan changes it), so a throttled staging, about 200 s, or approve, about 320 s, is cut by the proxy before gunicorn's 120 s, and gunicorn's timeout decides nothing. Default: both requests stay synchronous and one transaction each, the server finishes the work after a cut, and the pages poll for the result as section 6 says. The alternatives are a `staging` and an `applying` batch status answered with 202 and polled from the start, which changes F1's rejected-with-no-batch contract, or asking Fly support for a longer idle timeout.
2. Where it lives: `apps/demo` mounted at `/api/v1/admin/`, `reset-demo/` (GET the counts, POST the reset), `sample-files/` and `sample-files/{name}/`.
3. Which employees a generated file takes: current employees of its share by id whose latest live record is dated before the file's effective date, promotions among those below L6, exits among those still employed. Shares: 0 diwali-bonus, 1 april-raises, 2 promotions, 3 exits, 4 fix-me, newhires none.
4. A file imported twice is a no-op for all six only if a row that repeats a scheduled revision counts as one: april-raises' second import is dated on the scheduled revision its first made, today the `effective_from must be after` error. Default: one more section 7 row, a row whose `effective_from` and amounts repeat a live record dated that day is a `noop`.
5. The cap counts the rows classified `create` that are not errors, plus the employees in the database, at staging only. Two batches in review could together pass 25,000, and approve does not re-check.
6. A reset during an approve waits up to 20 s on SQLite's write lock, then is a 500. Default: accept, and the 409 covers an upload being read, as asked.
7. Audit: `demo_reset` joins `AuditLog.Action` through a choices-only migration, employee and batch null, the actor the user, `before` the counts, `after` empty.
8. The base file is written by `--base` from the generator without a database, every row `effective_from` at joining and leavers with `last_date`, in joining order with the seed's legacy codes. Its test regenerates 15,000 entries, about 10 s, so it is marked `slow` like the golden hash.
9. `--raises` draws 3 to 8% per row from the seed in place of a fixed 5% and takes `--effective`, so the step 5 sample files are regenerated once more and their tests follow.
10. The generated files' names on disk are the owner's, `?seed=` defaults to 42 and the page passes none, so a file is deterministic for a database and a day.
11. The Dockerfile copies `sample-data/base-15000.xlsx` into the image and `SAMPLE_DATA_DIR` names the folder, the repository's locally.
12. Timing: `timing --case demo-files` generates each on-demand file on the seed and prints its time and rows; `timing --case base-import` creates a scratch database with the HR user, stages and approves the base file through the API, not rolled back, and prints both times and the peak; on Fly it runs once with the balance in hand and once with it spent.
13. The page's wording as section 6 has it, the dialog's counts in words, and REQUIREMENTS gains in-scope item 10.

Step 9 (D64) assumed these defaults. The owner approved them on 8 October with changes: 1 keeps level on the employee, with the caption `Levels are as of today; anyone promoted after <to> appears at their new level` on the three cards that group by level when `to` is not today and a level history per record added to P1; 4 has L1 leave twice as often as L3 to L6 and L2 one and a half times; 7 starts Last N months on that month's last day where the day does not exist, amended by D69 to the day after it; 10 times the seed on Fly, raising its target to 120 s if it takes over 60 s, and runs `reset_demo` on the live machine only on the owner's word, after it has been idle; and 12 is replaced by a 15,000-row import limit, `make_import_file --all` writing everyone. 2, 3, 5, 6, 8, 9 and 11 stand.

1. Level history. Level and designation are fields of the employee, not of a pay record, so on an earlier `to` the cards that group by level (by-level, by-tenure's Level, gender-gap's By level) use each person's level today, or on their last day. Each promotion is named in its record's note. Default: keep level on the employee and caption those cards `levels as of today` when `to` is not today. A level per record would be a schema change across the import, the API and the forms.
2. Promotions fall on April revisions, so a level follows the experience at the last review (1 April, or the joining date since), not today's, and someone can sit up to six months past their range until the next April. Default: today's level is drawn on the experience at the last review, so every active L1 joined after 1 April 2023, about 3.5 years before the reference date. The other way is a promotion on the day experience crosses its point, which would not be an April revision.
3. L1 and L2 meet at 3 years with no overlap, unlike the other neighbours. Default: the L1 to L2 promotion is the first 1 April at 3 years or more. The other way is L2 from 2 years, overlapping like the rest.
4. Juniors leave more often. Default: the leavers' levels are drawn with L1 and L2 weighted 1.5 times L3 to L6.
5. The leaver flow. Default: the 5,000 last days spread over the months in proportion to the active headcount at each month's end, by largest remainder so the total is exact. The yearly rate then follows from the two counts and the hiring curve, about 10% by estimate, measured in the build. If it falls outside 8 to 10%, the owner chooses whether to change the exited count.
6. The API's `status` default. Default: Active as well, as D63 did for the order, so a directory request or export without `status` holds the 10,000, and `status=any` returns everyone.
7. Presets read today in UTC, the API's reporting date. Last N months runs from the same day N months back (amended by D69: from the day after it) (28 February for a 29, 30 or 31) to today, Current FY to date from the 1 April that opened today's financial year, and Last FY is the 1 April to 31 March before that.
8. Spend in period. Default: a day costs the annual figure divided by the days in its calendar year, so a whole calendar year costs exactly the annual figure, and the headcount for D59 is everyone employed on any day of the period.
9. Back-filled pay can fall below today's country minimum in someone's early years, today's pay divided by every raise since. The minimum is a warning, not an error. Default: keep the history the raises imply.
10. Seed time. About 15,000 employees and 60,000 records, roughly 18 s on the laptop and perhaps 70 s on Fly's shared CPU, over the 60 s target there. Default: time it on Fly before `reset_demo` runs there, and tune the bulk writes only if it misses.
11. The experience premium is measured at the last review, the record's own start, since pay changes only at a revision.
12. `make_import_file --all` writes the 10,000 active employees, the import's limit, so the import timing stays a 10,000-row file.

Step 8 (D62) assumed these defaults. The owner approved them on 8 October with changes: 1 became the three headings in section 8 above, 2 became Include exited not applying to `trend` and `cost-bridge`, 4 now has the pay changes summed from those who stayed as well, held within 3 cents per currency of the balancing figure that the card and the export show, 8 now has the export carry both figures, and 6 stands with D62's note on the UK method. 3, 5 and 7 stand, and at the step 8 close 6 was narrowed to rank women and men alone (D62).

1. Card order on the dashboard as in section 8 above: trend first under the KPI row, the gender card last.
2. `include_exited` applies to every date of `trend` and `cost-bridge`, so someone who left during the bridge's year stays in its end population at their last record and is not a leaver.
3. Tenure for someone who left is measured to their last date.
4. The bridge's pay changes takes any sub-cent rounding, so the parts add up to the cent.
5. cost-mix lists countries by name, and each share is rounded to one decimal on its own.
6. Quartile ties are broken by employee id, and the cuts fall at `floor(k * n / 4)`.
7. The bonus gap's reason counts those with a bonus: `fewer than 5 women with a bonus`.
8. `trend` always returns both figures, and `measure` picks the line and the export's columns.

Steps 1 to 7: answered on 7 October 2026 and recorded in `docs/DECISIONS.md` D24 to D30. The sections above already reflect the answers.

1. Approve after the data changed: the default, those rows re-marked `error`, the batch stays in `review`, 409 with the rows (D24).
2. By-level under five people: the general rule, SPEC section 9 corrected (D25). Since raised to twenty people, with p10 to p90 (D59).
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
