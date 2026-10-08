# Security audit of 8 October 2026: triage

The Cloudflare security-audit skill ran statically on commit `678cbb7` (the step 9 approval), with no target execution: `REPORT.md` is copied below unchanged, with `NEEDS-VALIDATION.md` and the ten pytest leads of `tests/security/` beside it in the audit's own folder. Nothing was confirmed and 14 leads needed validation. The pytest leads now live in `backend/tests/security/`, marked `xfail(strict=True)` by the audit, where XFAIL meant the weakness was present and XPASS that it was absent or fixed. In step 11 (D73) each lead was run and settled as the table says: where it is fixed or already fixed the marker came off and the test guards the fix, where it is accepted the marker stays with a reason that names this review.

Owner decision: triaged on 9 October 2026 (D73).

## Triage, lead by lead

| Lead | Triage | Test |
| --- | --- | --- |
| Login throttle trusts client-sent `X-Forwarded-For` when no proxy is in front (compose) | Fixed, step 11 commit `fix(security)`: `NUM_PROXIES` from the environment, default 1 for Fly, compose sets 0 and publishes `127.0.0.1:8000:8000` | `test_settings_num_proxies_xff_trusted_without_proxy.py`, both values guarded |
| Changing the HR Manager password does not end sessions whose refresh token predates it | Accepted: the operator rotates the password with `changepassword` and then `revoke_sessions`, the README's operator note | `test_accounts_password_change_keeps_refresh_token_valid.py`, xfail kept |
| Refresh-token rotation is a non-atomic check-then-act | Fixed, step 11 commit `fix(security)`: `rotate()` re-checks the blacklist inside one transaction, which SQLite opens for writing at once, and the serializer answers the race as a reuse, 401 and every session revoked | `test_accounts_rotate_not_atomic.py` guards |
| Login throttle folds every IPv4-mapped client into one `::/64` bucket | Fixed, step 11 commit `fix(security)`: `LoginRateThrottle.get_ident` unmaps `address.ipv4_mapped` before the /64 grouping | `test_accounts_login_throttle_ipv4_mapped_collapse.py` guards |
| Slow-header clients can hold all 8 gthread threads | Accepted: Fly's proxy fronts the live app and compose is local | none |
| Import level-cell parsing runs quadratic `int(Decimal())` on a cell of unbounded length | Already fixed (D68): every cell is clipped to 256 characters at read, so a longer level cell never matches as a number and never reaches `Decimal`; the lead XPASSed on its first run | `test_imports_parse_level_superlinear_int_conversion.py` guards |
| Directory CSV: a semicolon in a later column can start a formula where Excel splits on semicolons | Accepted: the writer escapes the standard triggers and quotes every field, and the split needs a reader whose list separator is `;` and that reopens a quote mid-field, a specific Excel locale | `test_exports_csv_semicolon_split_formula.py`, xfail kept |
| `make_import_file` writes spreadsheet-author text unescaped into `.csv` files | Fixed, step 11 commit `fix(security)`: CSV text cells go through `exports.writers.escape_cell`, numbers stay numbers | `test_imports_make_import_file_csv_formula_injection.py` guards |
| Agent deny and ask rules bypassed by auto-approved code execution | Accepted: a settings-level guardrail lead. The `.claude` rules protect one developer from the agent's mistakes on his own machine, not a security boundary, as the 6 October spec review says, and the gate is the owner approving each step | none |
| Agent can rewrite its own guardrail files | Accepted: the same | none |
| `git_guard` lets shell-valid spellings of history rewrites through | Fixed, step 11 commit `chore(hooks)`: soft, keep and mixed resets and every spelling the audit lists are blocked | `test_git_guard_history_rewrite_regex_bypass.py` guards from that commit |
| Commit gate fails open for commits spelled with another global option | Fixed, step 11 commit `chore(hooks)`: any global option is detected, pytest exit 5 fails, `tsc -b` runs, and any exception exits 2 | `test_pre_commit_gate_commit_detection_bypass.py` guards from that commit |
| SessionStart hook reports a review as approved when reviewer text quotes the phrase | Fixed, step 11 commit `chore(hooks)`: the approval is read from line 3 only, and the latest review is picked by file name | `test_session_start_review_approval_from_model_text.py` guards from that commit |
| Untrusted ingested content can reach unprompted actions | Accepted: the same settings-level reason | none |
| Deferred: aggregate PBKDF2 cost of admitted logins across many addresses | Accepted: deferred by the audit itself, the per-address throttle stands and D41 rejected lockout | none |
| Blocked: advisory status of the locked dependencies | Settled, step 11 commit `build`: CI runs `npm audit --omit=dev` and `uvx pip-audit` on the locked runtime dependencies and fails on any known vulnerability, both clean on 8 October | CI |

## The audit's hardening notes

Taken in step 11: compose on `127.0.0.1`, `DATABASE_PATH` required in production, the test `SECRET_KEY` refused, actions pinned by commit SHA with `persist-credentials: false`, only the runtime directories in the image, the three unclipped echoes clipped and a fixed `error_summary`, `safeNext` refusing a path that starts with `//`, a throttle scope and JSON only on refresh, the preflight's zip parts capped, `XFrameOptionsMiddleware` above WhiteNoise, `--` before paths in `post_edit.py`, the latest review by file name, `disable-model-invocation` on `/finish-step`, the operator note on rotating the HR password, and an unprivileged user in the image.

Not taken, recorded here: base images stay on tags rather than digests, so a rebuild picks up Debian's security updates; the exchange rate is still resolved after a write commits (a `MissingRate` turns an audited write into a 400, D13's accepted shape); the login throttle keeps DRF's cache read-check-write with one worker; releases are still deployed by the owner from a clean tree rather than from a CI-built image; the commit gate tests the working tree, as the owner commits with `git add -A`; reviewer subagents keep read-only Bash; `set_exchange_rate` keeps its current checks; `reset_demo` and `seed_data --reset` ask for no confirmation, being the owner's own commands; no-store stays keyed as it is; the Emotion cache keeps `style-src 'unsafe-inline'`; and compose runs no reverse proxy, being local.

---

# Security audit report: acme-audit

## 1. Run scope and limits

- **Target:** `/Users/nutanprabhat/MyProjects/IncubyteScreening/acme-audit`, branch `main` at commit `678cbb7d19ba` (clean tree).
- **Profile:** `standard`. **Scope:** the whole repository. **Budget:** none set. **Agents spent:** 60 agent invocations: 4 reconnaissance, 15 hunters across five waves, 5 coverage critics, 22 candidate verifiers (20 plus 2 fresh re-runs after malformed results were discarded), and 14 final-record verifiers.
- **Execution:** static only. This host could not enforce the sandbox the audit method requires (no OS-enforced memory cap, Docker daemon down, no project virtualenv), and the owner chose not to execute target code. The audit never ran project code, tests or builds. Every runtime-dependent lead is therefore `needs_validation` and comes with a ready-to-run check.
- **What still ran:** the repository's own `.claude` hooks executed on this session's tool calls, as part of the owner's harness. Once, a read-only search containing git's commit subcommand triggered `pre_commit_gate.py`, which ran nothing because no virtualenv exists.
- **Library source:** From critic c2 onward, agents read pinned third-party source read-only from ~/.cache/uv (archive-v0 wheels whose sha256 matches backend/uv.lock) and ~/.npm/_cacache, and the local CPython 3.14 standard library; nothing was imported or executed and ../acme-salary was never used.
- **Static aids:** Two verifiers evaluated an extracted regex literal (pre_commit_gate.py line 28) and the stdlib ipaddress fold on literal strings with stdlib-only Python; no project module was imported or executed.
- **Prior runs:** none. No record was carried, excluded or revalidated.
- **Coverage stop:** explicit early stop after hunter wave 5 and post-wave critic c5-postwave. Time-bounded run: each of the five critic rounds found further gaps; the remaining proposed unit is deferred and disclosed. No final-clean critic ran, so no complete-coverage claim is made. This is a partial-coverage report.
- **Interruptions:** four wave-1 hunters stopped on a transient API DNS error and were resumed with their context intact.

## 2. Security posture

The application is carefully built.

- Every API route except login and refresh requires a JWT, and a test pins all 25 routes.
- There is no cookie or session authentication, so there is no CSRF surface, and CORS uses an exact-match allowlist without credentials.
- The CSP blocks inline and third-party script, and the frontend has no HTML or eval sinks.
- The spreadsheet parser refuses XML entities and external links and enforces decompression budgets.
- Production settings fail closed on a missing or placeholder secret.

Verification refuted 6 of the 20 candidates. Three were refuted by reading the locked library source: React Router 8.4.0 blocks off-origin navigation, and Django and DRF bound request bodies (two candidates). Three more involve no lower-trust actor: deploy provenance, the commit gate's staged index, and Bash in the reviewer subagents.

14 source-grounded leads remain. None is confirmed, because this run executed no code. Each comes with a ready-to-run check.

- **Login and session controls (four leads).** The two most consequential:
  - Under docker compose the login throttle trusts a client-sent X-Forwarded-For, which removes the brute-force limit on the fixed account `hr@acme.example`.
  - Changing the HR Manager's password does not end sessions that already exist.
- **Availability (two leads).** Slow-header clients can starve the single 8-thread gunicorn worker. A long all-digit `level` cell is converted quadratically during import.
- **Spreadsheet formula injection (two leads).** These are second-order paths from imported names into files opened in Excel.
- **Claude Code guardrails on the developer machine (six leads).** The hooks and permission rules this repository relies on can be bypassed, or edited, by the agent they are meant to constrain. Prompts the owner treats as approvals, such as `fly deploy`, can be reached through the auto-approved `uv run *` prefix.

## 3. Confirmed findings

None. In a static-only run, `confirmed` needs a decisive effect observable in tracked bytes without executing code. No candidate met that bar, so nothing below carries a severity.

## 4. Needs validation

These are source-grounded leads whose decisive fact could not be observed in this run. They are not confirmed vulnerabilities and carry no severity. Each lead with a pytest file has it at `tests/security/test_<id>.py`, written to run unchanged from `backend/`. Every one of those tests is marked `xfail(strict=True, raises=AssertionError)`: XFAIL means the weakness is present, and a strict XPASS failure means it is absent or fixed. The marker exists so that adding the tests cannot block the project's commit gate. Full traces and plans are in `NEEDS-VALIDATION.md`. A blocker or plan that names `lead_01.py` means the verifier's working copy of that lead's test, delivered as `tests/security/test_<id>.py`.

### Login and session controls

These are the production-facing leads. For docker compose, running its test settles the X-Forwarded-For lead. Whether it also applies on Fly depends on how fly-proxy writes the header, which needs observation, not traffic.

| Lead | Where | Exact blocker | Local next step | Owner-observed check |
|---|---|---|---|---|
| **Login throttle trusts client-sent X-Forwarded-For when no proxy is in front (docker compose mode)** (`settings_num_proxies_xff_trusted_without_proxy`) | `backend/apps/accounts/views.py:37` | Who can reach port 8000 of a compose host is not source-visible. docker-compose.yml:7 names no host address, so Docker publishes on every interface by default, but whether other machines can connect depends on the host firewall and on Docker's daemon or Docker Desktop settings.; Whether the live Fly app shares the weakness is not source-visible. It depends on how fly-proxy writes X-Forwarded-For: appending the connecting address as the last element keeps NUM_PROXIES = 1 correct there. This decides only the Fly scope, not the compose result, and must be settled by observation, not by sending test logins to the live app. | `test_settings_num_proxies_xff_trusted_without_proxy.py` | Observation only; no requests go to any shared deployment. Compose host (the owner's own machine, with the stack up): read `docker compose port app 8000` and the listening sockets (`lsof -nP -iTCP:8000 -sTCP:LISTEN` on m... |
| **Changing the HR Manager password does not end sessions whose refresh token was issued before it** (`accounts_password_change_keeps_refresh_token_valid`) | `backend/apps/accounts/serializers.py:42` | The decisive fact, that a refresh token issued before a password change still rotates at /api/v1/auth/refresh/ into an access token that /api/v1/auth/me/ accepts, is settled by the pytest lead (lead_01.py), which was written but not run in this static-only pass. | `test_accounts_password_change_keeps_refresh_token_valid.py` | No live request is needed: settings/prod.py does not override SIMPLE_JWT and the image runs the prod settings (Dockerfile:18), so the local test settles the deployed behaviour. Owner-observed only: check whether the oper... |
| **Refresh-token rotation is a non-atomic check-then-act, so simultaneous presentation of one token can bypass reuse-detection revoke-all** (`accounts_rotate_not_atomic`) | `backend/apps/accounts/services.py:24` | Whether two requests can both pass token_class() before either rotate() commits its blacklist write, under SQLite WAL and the 8-thread gthread worker, is a runtime/timing fact that must be observed with concurrent requests against a local instance; source establishes the non-atomic check-then-act but not that the race window is actually hit. | `test_accounts_rotate_not_atomic.py` | - |
| **Login throttle folds every IPv4-mapped client into one shared ::/64 bucket** (`accounts_login_throttle_ipv4_mapped_collapse`) | `backend/apps/accounts/views.py:30` | Deployment fact: whether the Fly edge writes an IPv4 client's address into the X-Forwarded-For hop that DRF reads (the last hop under NUM_PROXIES = 1) as an IPv4-mapped literal ('::ffff:a.b.c.d') or as a dotted quad is not source-visible. The AF_INET bind in entrypoint.sh:11 rules out a mapped REMOTE_ADDR, so this edge behaviour is the only production route; if the edge writes dotted quads, the collapse is unreachable on Fly and the item is latent hardening only. | `test_accounts_login_throttle_ipv4_mapped_collapse.py` | Observation only: send no test, attack or repeated login traffic to the shared Fly app. Establish the textual form the Fly edge uses for an IPv4 client in the X-Forwarded-For hop it appends (the last hop). First read Fly... |

### Availability

Both hold a thread of the only gunicorn worker. The import lead needs an authenticated upload of an untrusted author's file. The slow-header lead needs no authentication at all.

| Lead | Where | Exact blocker | Local next step | Owner-observed check |
|---|---|---|---|---|
| **Slow-header clients can hold all 8 gthread threads of the single gunicorn worker with no read deadline** (`gunicorn_gthread_slow_header_thread_starvation`) | `entrypoint.sh:14` | The decisive effect -- all 8 pool threads held, a concurrent well-formed request stalling, and the arbiter not murdering the worker -- is gthread socket/thread-pool behaviour that Django's in-process test client never exercises; confirming it requires running gunicorn against raw slow-client sockets, which is disallowed here (no target execution, no importing gunicorn).; Whether Fly's edge proxy fully buffers request headers before contacting the origin is not source-visible; if it buffers, the Fly path is shielded, but the docker-compose path exposes gunicorn directly regardless. | No pytest lead file is provided: the weakness lives in gunicorn's gthread worker and its blocking socket.recv header loop, which pytest-django's in-process APIClient does not exercise, and importing or running gunicorn i... | Observation only, no test traffic: from Fly proxy documentation or the rendered edge/service configuration, confirm whether full request headers are buffered before the origin is contacted (which would shield the Fly pat... |
| **Import level-cell parsing runs quadratic int(Decimal()) on a cell of unbounded length** (`imports_parse_level_superlinear_int_conversion`) | `backend/apps/imports/parser.py:377` | Source establishes only the complexity class (library:cpython@3.14.3/Lib/_pylong.py:287-290). The magnitude under the C _decimal module is unmeasured: CPU time per level cell as its length grows to the 131,072-character CSV limit, the total for one upload within the 10 MB cap, whether that approaches gunicorn's 120 s --timeout, and how long the _reading lock is held. Timing experiments are forbidden in this run.; The deployed image's decimal implementation was not inspected, because the Docker daemon is down. decimal.py prefers the C module and both local 3.14 builds ship it. If the image lacked _decimal, a cell past 4,300 digits would raise ValueError (a 500) instead of converting. | `test_imports_parse_level_superlinear_int_conversion.py` | Observe only, from the app's own logs and Fly readouts, with no crafted traffic to the live app. Look for a gunicorn '[CRITICAL] WORKER TIMEOUT' line or a worker restart during an import, and for /healthz check failures ... |

### Spreadsheet formula injection

Both start with text from an imported spreadsheet and end in a CSV that someone opens in a spreadsheet application. The XLSX and JSON exports are not affected.

| Lead | Where | Exact blocker | Local next step | Owner-observed check |
|---|---|---|---|---|
| **Directory CSV: a semicolon in a later column can start a formula cell where Excel splits on semicolons** (`exports_csv_semicolon_split_formula`) | `backend/apps/exports/writers.py:59` | Third-party behaviour not visible in the repository: whether Excel, opening a .csv by double-click in a locale whose list separator is ';', treats a double quote that follows a closed quoted section as text, as Python's csv reader does with strict off, and so splits at a ';' inside a later quoted comma-field; and whether it then evaluates the resulting =... cell on open, including in Protected View for a downloaded file. A reader that keeps a quote not followed by its separator inside the quoted field, as LibreOffice Calc may, keeps the whole line in one cell and does not split. | `test_exports_csv_semicolon_split_formula.py` | - |
| **make_import_file writes spreadsheet-author text unescaped into .csv files** (`imports_make_import_file_csv_formula_injection`) | `backend/apps/imports/management/commands/make_import_file.py:176` | Whether a spreadsheet application evaluates, or prompts for, a .csv cell whose text starts with = or @ is third-party behaviour outside source.; Whether the operator ever writes a make_import_file .csv from a database that holds approved third-party sheets and opens it in a spreadsheet application is operator practice outside source: the documented .csv use is the sample built from seeded data (docs/DECISIONS.md:247), and the /perf-timing import case, the one run on the live machine, writes a temporary .xlsx (backend/apps/core/management/commands/timing.py:242). | `test_imports_make_import_file_csv_formula_injection.py` | Owner observation only, with no requests to the live app and no test data on it: state whether make_import_file has been or will be run with an --out ending in .csv against the live database (fly ssh console) or a copy o... |

### Claude Code guardrails (developer machine)

These concern `.claude/`, not the deployed app. The principal is the coding agent itself, acting by mistake or steered by content it reads, such as logs, fetched pages or Context7 docs. Several leads share one root, the auto-approved `uv run *`, `npm run *`, Edit and Write rules. One settings change (an OS-level Bash sandbox, or narrower allow rules plus ask rules on `.claude/**` and `CLAUDE.md`) addresses most of them.

| Lead | Where | Exact blocker | Local next step | Owner-observed check |
|---|---|---|---|---|
| **Agent deny and ask rules (.env read, curl/wget, deploy) bypassed by auto-approved code execution under uv run \* and npm run \*** (`claude_permissions_deny_ask_bypassed_by_code_exec`) | `.claude/settings.json:106` | Claude Code's permission decision is harness behaviour, not repository source. Two questions stay open. First, does Bash(uv run *) auto-approve `uv run python -c '<code>'` and `uv run --env-file .env <command>` with no built-in prompt? Second, is a Read-path deny ever applied to a file that a Bash subprocess opens? The repository's reviews quote the documentation (prefix matching, not a security boundary: docs/reviews/spec-review-2026-10-06.md:201), but they record no observation of this case.; Machine state outside the tracked tree cannot be read in this run. It includes whether the owner's untracked .claude/settings.local.json, user settings or managed settings enable a Bash sandbox, or add rules that would limit the subprocess's file and network access. It also includes whether backend/.env exists and whether it holds only local values. | No pytest lead file applies. The deciding fact is Claude Code's permission decision on a Bash call, and no Django test under backend/ can observe it. Instead, run this owner-observed check. It is non-destructive and uses... | - |
| **Agent can rewrite its own guardrail files: no ask or deny rule covers .claude/hooks, .claude/settings.json or CLAUDE.md under the unscoped Edit/Write allow** (`claude_permissions_guardrail_files_writable`) | `.claude/hooks/git_guard.py:38` | Claude Code behaviour not contained in the repository: does the installed version apply its built-in safeguard for writes to its own configuration ahead of the unscoped Edit/Write allow? Its documentation, which this run could not re-read (no network), describes protected directories, including .claude/ with exceptions for content folders such as .claude/agents and .claude/skills, whose writes are not auto-approved; whether that also overrides an explicit allow rule is the open point. If the safeguard covers .claude/hooks/*.py and .claude/settings.json, those legs are refuted for that version, and only CLAUDE.md and .pre-commit-config.yaml stay editable with no prompt. The Claude Code installation is outside the target, so this run could not read it.; The effective permissions also merge the user-level ~/.claude/settings.json and any managed policy settings. Both are outside the repository, could add ask or deny rules for these paths, and are not visible here.; It is unknown whether an edit to .claude/settings.json changes hooks or permission rules inside the running session; the documentation says hook configuration is captured at session start. Either way the edited file governs the next session. This affects only the in-session effect of the settings.json leg, not the hook-script leg. | No pytest lead file. The decisive facts are how Claude Code handles permissions and hooks, which a Django test cannot observe. The owner runs this check in a throwaway clone and pushes nothing. (1) Clone the repository a... | - |
| **git_guard lets shell-valid spellings of reset --hard, force push, rebase and --amend through** (`git_guard_history_rewrite_regex_bypass`) | `.claude/hooks/git_guard.py:47` | What follows the hook's exit 0 is outside the repository: whether an unblocked spelling then runs without a prompt depends on the permission mode of the owner's Claude Code sessions, on how Claude Code matches the allow rules Bash(git commit *) and Bash(uv run *), and on settings this audit cannot see: the owner's user-level settings and any gitignored .claude/settings.local.json in the working copy (.gitignore:23), which this clone does not have. | `test_git_guard_history_rewrite_regex_bypass.py` | Optional, observation only, not needed to settle the lead: in the hosting settings of the remote that the owner's working repository pushes to (GitHub, given .github/workflows/ci.yml; this audit clone's origin is a local... |
| **Commit gate fails open for git commits spelled with a global option other than -C/-c** (`pre_commit_gate_commit_detection_bypass`) | `.claude/hooks/pre_commit_gate.py:29` | Tracked source does not show whether the owner's working clone has the pre-commit framework's git hook installed. `.pre-commit-config.yaml` takes effect only after `pre-commit install`, and this audit clone has neither .git/hooks/pre-commit nor core.hooksPath. If the hook is installed, git runs the same gate for `git --no-pager commit -m x`, and an unchecked commit then also needs a way past git's hook, such as `-n`, a hooks-path override or SKIP=acme-gate.; Whether a non-canonical spelling runs without the owner's approval depends on the session's permission mode, on user-level settings, and on how Claude Code matches `Bash(uv run *)` against a wrapped git command. None of these is visible in the repository. | `test_pre_commit_gate_commit_detection_bypass.py` | - |
| **SessionStart hook reports a spec review as owner-approved when reviewer-written text quotes the approval phrase** (`session_start_review_approval_from_model_text`) | `.claude/hooks/session_start.py:80` | Model behaviour: whether the web-fetching reviewer, by its own wording or steered by a fetched page, places 'Owner decision: approved' within the first 600 characters while line 3 is not approved. Neither committed review does: inside the window the phrase appears only on the owner-edited line 3.; Model behaviour: whether a later session acts on the hook's 'Spec review gate: approved' line, in /start-step's gate after a planning document changes or in /plan-and-design when the owner invokes it, instead of reading line 3. Both gates are prose that the model evaluates. | `test_session_start_review_approval_from_model_text.py` | - |
| **Untrusted log/doc/web content a session ingests can reach unprompted code execution and file writes with no provenance gate** (`ingested_logs_docs_drive_unprompted_actions`) | `.claude/settings.json:25` | Whether the agent model acts on instructions embedded in ingested log/doc/web text (rather than treating it as data) is LLM behavior, not determinable from source.; The degree to which an anonymous client can place chosen, legible text into the `fly logs`/`docker compose logs` stream (log levels, formats, Django arg escaping and gunicorn access-log settings at runtime) is a deployment/runtime observation. | No project pytest can settle this: the secure invariant (untrusted ingested content must be separated from, or gated before, allow-listed agent side effects) lives in the Claude Code harness and .claude/settings.json, no... | Owner-observed: in existing Fly logs, confirm whether request-derived fields an anonymous client controls (the Host header on a 400/DisallowedHost, the refresh-reuse subject, an import error_summary/traceback) are presen... |

## 5. Hardening notes and positive patterns

**Hardening** (not findings: no lower-trust principal reaches a security consequence today):

- **Container and compose:**
  - Run the image as a non-root user; PLAN step 10 already schedules this.
  - Publish compose on `127.0.0.1:8000` instead of every interface.
  - Require `DATABASE_PATH` in prod settings, so a missing Fly secret cannot silently put the database on the ephemeral root filesystem.
  - Add the repository's own test `SECRET_KEY` values to prod's refused placeholders.
- **Build inputs:**
  - Pin `node:26-slim`, `python:3.14-slim` and the uv image by digest, and the GitHub Actions by commit SHA.
  - Set `persist-credentials: false` on checkout.
  - Copy only the runtime directories into the image; `backend/tests` and `.env.example` ship today and are inert.
- **Echoes and error text:**
  - Route the three unclipped echoes through `clip()`: the `Unknown country_code` 404 message, django-filter's invalid-choice text, and the JSON export's `filters` object.
  - Store a fixed user-facing `error_summary` instead of raw exception text. The traceback is already logged.
- **Navigation guard:** have `safeNext` return `/` when the resolved pathname starts with `//`, and add the three dot-segment inputs to `navigation.test.ts`. React Router 8.4.0 blocks the redirect today, so this keeps the guard honest for any future sink.
- **Refresh endpoint:** add a throttle scope and restrict its parser to JSON. Body size is already bounded by Django's 2.5 MB default.
- **Import parser:** cap the character length of numeric cells at read time, which also closes the `parse_level` lead, and cap the number of zip entries the preflight scans.
- **Write ordering:** resolve the reporting exchange rate before a write commits. A `MissingRate` currently turns a committed, audited write into a 400 response.
- **Login throttle:** use an atomic counter or a short lock instead of DRF's list read-check-write. Raise or dedicate the LocMemCache `MAX_ENTRIES`. Consider a per-account counter that alerts rather than locks, since D41 rejected lockout.
- **Release provenance:** deploy only from a clean tree at a pushed, CI-green revision, or from a CI-built image by digest, and stamp the revision into an image label. Set `disableBypassPermissionsMode` so the `fly deploy` prompt cannot be switched off. This was rejected as a vulnerability: the agent that edits the tree can also commit it.
- **Commit gate:** test the staged index (`git checkout-index` into a temporary directory) or refuse when the tree is dirty. Treat pytest exit 5 as a failure. Add `tsc -b`, the only type check, which the gate skips today. The staged-index candidate was rejected as a quality gap, not a boundary crossing.
- **Agent tooling:**
  - Limit reviewer subagents' Bash to git inspection.
  - Set `disable-model-invocation` on `/finish-step`.
  - Pass `--` before paths in `post_edit.py`.
  - Choose the latest spec review by file name, not modification time.
- **Operator commands:**
  - `set_exchange_rate` should refuse non-finite, over-precise or out-of-range rates and record an actor.
  - `reset_demo` and `seed_data --reset` should ask for confirmation.
  - Document that rotating the HR password means `changepassword` followed by `revoke_sessions`. Changing `SEED_ADMIN_PASSWORD` never changes the live login.
- **Headers:**
  - Place `XFrameOptionsMiddleware` above WhiteNoise, so static files also carry the header; CSP `frame-ancestors 'none'` already covers modern browsers.
  - Key no-store on `request.path_info`.
  - Consider a nonce-based Emotion cache to drop `style-src 'unsafe-inline'`.
- **Front proxy:** put a buffering reverse proxy or a header-read timeout in front of gunicorn in compose. This bounds the slow-header lead independently of gunicorn.

**Positive source patterns** that hold up under review:

- Global `IsAuthenticated` with JWT-only authentication, plus `tests/test_auth_coverage.py`, which pins all 25 routes and requires 401 on every method for the 23 protected ones.
- No cookies or session authentication, so there is no CSRF surface. CORS uses an exact-match origin list with credentials off, and tokens are sent only to the app's own origin.
- A strict CSP: `script-src 'self'`, `object-src 'none'`, `base-uri 'none'`, `frame-ancestors 'none'`. zod runs jitless and there are no `innerHTML`, `eval` or `dangerouslySetInnerHTML` sinks. Every server string renders as React text.
- The spreadsheet preflight refuses any XML entity declaration, caps unpacked bytes, elements, rows and columns, never follows external links, and reads only the first sheet. Tests cover each of these.
- Production settings force `DEBUG` off and refuse a missing, short or placeholder `SECRET_KEY`, `ALLOWED_HOSTS` or `SEED_ADMIN_PASSWORD`. No credential was ever committed, including in history.
- Refresh rotation keeps the original session end and revokes every session on reuse. Login returns one constant 401 and runs the password hasher for unknown emails too, so it offers no enumeration oracle.
- Every pay write is atomic and audited, and no row is ever deleted. The cancelled-record predicate is applied in every live query, totals are computed on the server, and the import validators are shared with the API and the seed.
- ORM only, with allowlisted ordering and filters. No raw SQL is reachable from a request.
- Locked libraries back the design. gunicorn 26.2.0 rejects every classic request-framing vector at its defaults, and h2c is off. React Router 8.4.0 refuses external navigation. Django bounds both JSON and multipart bodies.
- CI runs with `contents: read` and no secrets, and pull-request code gains no privilege. Both lockfiles carry hashes, and builds use `uv sync --frozen` and `npm ci`.

## 6. Coverage

The ledger has 60 coverage units: 2 blocked, 21 candidate, 36 covered, 1 deferred.
Final records: 0 confirmed, 14 needs_validation, 6 rejected.

**Blocked units** (owned partial review with an exact external blocker):

- third-party packages and base images shipped in the image / Obvious things (ATTACK-CLASSES.md): Advisory-database status (OSV, GitHub Advisory Database, PyPA, npm audit) of locked versions released after this review's offline knowledge, notably Django 6.1.2, gunicorn 26.2.0, djangorestframework 3.18.3, PyJWT 2.15.1, django-filter 26.2, react and react-dom 19.3.0, react-router 8.4.0, @mui/material 9.4.0 and @mui/x-data-grid 9.15.0. This run has no network and no advisory database. The owner can settle it on a machine with network access with an OSV or GitHub advisory scan of backend/uv.lock and frontend/package-lock.json (for example osv-scanner given both lockfiles, or `npm audit --omit=dev` plus pip-audit on `uv export --frozen --no-dev` output). Debian package and CPython patch levels in the python:3.14-slim image actually built for each deploy (libexpat1, zlib1g, libsqlite3-0, libssl), which the import parser exercises with spreadsheet-author input. Observe with `docker run --rm --entrypoint sh <image> -c "dpkg-query -W libexpat1 zlib1g libsqlite3-0; python -c 'import pyexpat, sys; print(pyexpat.EXPAT_VERSION, sys.version)'"` and compare with the Debian security tracker.
- requests Fly's proxy forwards to gunicorn 26.2.0 / Request framing and desynchronization (WEB-PROTOCOL-AND-AUTH.md): Fly edge-proxy request framing/normalization (multiple Content-Length, Transfer-Encoding handling, header-name normalization, CR/LF conversion) is not in the repository; a framing desync on the Fly path would require the proxy to parse differently from gunicorn 26.2.0, which conforms. Owner must observe the edge behaviour (Fly proxy docs / rendered config, or the exact bytes the origin receives in its own access logs) to close the proxy<->origin pairing. The docker-compose deployment has no proxy and is fully resolved.

**Deferred units** (not examined in this run):

- POST /api/v1/auth/login/ (public) / Pre-authentication work imbalance (RESOURCE-EXHAUSTION-AND-AVAILABILITY.md): Deferred by an explicit early stop after five hunter waves and five post-wave critics (parent decision, time-bounded run). Proposed by critic c5-postwave: aggregate PBKDF2-SHA256 (1,500,000 iterations) CPU cost of admitted login attempts across many idents (IPv4 addresses or IPv6 /64s within one allocation) on the burst-limited shared vCPU; no global bound beyond the per-ident 5/min throttle. Not examined in this run.

**Noted, not validated** (not findings; each needs its own check):

- A final verifier noted a possible separate root cause that was not validated in this run. `check()` in `.claude/hooks/pre_commit_gate.py` (lines 49-53) catches only `TimeoutExpired`. A malformed or non-executable `backend/.venv/bin/ruff` or `pytest`, which the unscoped Write allow can create, would make `subprocess.run` raise, and the hook would exit 1 rather than 2. Claude Code treats a non-2 exit as non-blocking, so this would disable the commit gate without touching `.claude/`. It needs its own validation before it counts as a finding.
- A final verifier noted that `git_guard.py` has no rule for `git reset --soft`, `--keep` or a mixed reset, which also move a branch back. This is a variant of the `git_guard` lead's rule-enumeration root cause, and it was not separately validated.

**Important exclusions:** The RPC and messaging, desktop and mobile, and memory-safety companions were excluded: there is no RPC or queue, no native app and no native code. Effects the single HR Manager role has on its own data are intended (D4) and were not treated as findings. The dependency-advisory unit stays blocked because this offline run has no advisory database; run `osv-scanner` or `pip-audit` on `backend/uv.lock`, and `npm audit --omit=dev` on `frontend/package-lock.json`.

**Critics:** Five post-wave critics ran, and each found further gaps. They added 11 coverage units and sent 3 back for another pass. The run stopped explicitly after the fifth critic. One proposed unit is deferred: aggregate PBKDF2 cost on the login path. The distinct final-clean critic did not run, so this report makes no complete-coverage claim.

**Rejected candidates** (kept in `findings.json` so future runs do not repeat them): `accounts_refresh_unbounded_request_body`, `deploy_fly_working_tree_not_bound_to_commit`, `frontend_navigation_safenext_dot_segment_bypass`, `imports_upload_content_length_gate_trusts_client`, `pre_commit_gate_working_tree_not_staged_index`, `review_subagents_bash_overbroad_authority`.
