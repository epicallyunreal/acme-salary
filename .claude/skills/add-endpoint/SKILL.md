---
name: add-endpoint
description: Recipe for adding a DRF endpoint in this codebase, service first. Use whenever a new API route, view, serializer or filter is being added, or when the user says "add an endpoint", "expose X over the API" or "add a filter to the list".
---

# Add an endpoint

Check `docs/SPEC.md` section 8 first. The endpoint must be in the table with this method, path and parameters. If it is not, stop and ask. Do not add it to the spec yourself.

Order of work. Each numbered item is a test-first unit and usually its own commit.

1. Service. Put the behaviour in `apps/<app>/services.py` (writes) or `queries.py` (reads) as a plain function taking Python values and returning model instances or dicts. No `request`, no serializer. Write its unit tests in `tests/<app>/test_services.py` with `factory_boy` factories: happy path, each validation failure, and the invariant it protects (for example one current record per employee).
2. Serializer. Input serializer validates shape and types only: required fields, Decimal and date parsing, enum membership. It never imports `validators.py`; the service calls the validators and raises, and the view maps the raised messages to a `400` per field. Output serializer is read-only. Totals are never writable fields.
3. View. A thin `APIView` or `ViewSet` method: authenticate (default), parse params, call the service, return the serializer output. For lists use `PageNumberPagination`, `OrderingFilter`, `SearchFilter` and a `django-filter` `FilterSet` with the exact parameter names from the spec table. Use `select_related` and `prefetch_related` so one list request is a fixed number of queries.
4. URL. Register under `/api/v1/` in the app's `urls.py` with the spec's path.
5. API tests in `tests/<app>/test_api.py` with `APIClient`: unauthenticated request returns 401, happy path, each 400 and 409 case with the message asserted, and `django_assert_num_queries` on list endpoints.
6. Frontend hook. Add the typed request function and a TanStack Query hook in `frontend/src/api/`, plus an MSW handler in `frontend/src/test/handlers.ts`.

Error shape follows DRF: `400` per-field messages, `401`, `404`, `409` for state conflicts. Audit every write through `audit.record()` inside the service.
