# TaskOrbit diagnosis and free-resource improvement plan

Reviewed 3 October 2026. Scope: backend, browser code, models, authentication, dependency manifest, and deployment scripts. No application code or existing database data was changed. Tests used an isolated in-memory SQLite database. Production deployment, browser execution, restore capability, and load capacity were not tested.

## Assessment

Keep the existing FastAPI, SQLAlchemy, PostgreSQL and plain JavaScript architecture. A rewrite or paid service is unnecessary. The app has useful foundations: server-side assignment permissions, password hashing, request logging, task history, validation, and a production HTTPS proxy configuration. Fix the issues below before expanding deployment. Existing hardware, electricity, storage and administration still have costs; the plan requires no new software subscription or hosted service.

## Fix first

1. **High — logout does not clear the server cookie.** `app/static/index.html:381` sends no bearer header, although `/api/auth/logout` requires it. An isolated TestClient request with only a cookie returned 401 and no cookie deletion. Send the current authentication header before clearing browser state and handle failure. Longer term, use a single session mechanism with server-side revocation; a cookie-only design also needs CSRF protection. Verify logout clears the cookie and revoked sessions fail.

2. **High — employee names enter HTML without escaping.** `app/static/index.html:671`, `:681`, `:695` and related dropdowns interpolate names into `innerHTML`; employee CSV names are not restricted to plain text. This creates a stored script-injection path, with severity increased by authentication tokens in localStorage. Use DOM nodes and `textContent` for all employee-controlled text. Test that HTML-like names display literally. Source-confirmed risk; no browser exploit was executed.

3. **High — credentials and development behavior need separation.** `app/database.py:7` contains a database credential fallback using the postgres account. Require environment configuration, use a least-privilege application database user, and rotate the embedded credential if it is used anywhere. The local launch script does not set production mode; fresh development databases seed predictable demo accounts and expose the account directory. Provide an explicit secured intranet deployment configuration, stable secret, HTTPS, and no demo seeding. Production Compose already sets several of these controls.

4. **High — fresh installation dependency is wrong.** `requirements.txt:10` says `psycopg2-binary-2.9.13`. The requirement parser treats that entire string as the package name, with no version constraint. Replace it with `psycopg2-binary` and an appropriate, verified version constraint; validate installation in a clean environment and lock the tested dependencies. Existing `pip check` passes, but that does not validate a fresh install from this manifest. No package install was attempted.

5. **Medium — Assigned by Me returns no delegated tasks.** `app/main.py:512` first limits ordinary users to their own assignments; `:526` then requires the assignee to be a reportee. In a test with one delegated task, the hierarchy view returned 1 and Assigned by Me returned 0. Build a separate authorized query for this filter. Verify managers see their own delegated tasks and unrelated employees do not.

6. **Medium — reopened tasks retain completion dates.** `app/crud.py:55` sets completion once, but only clears it when returning to To Do. Done → In Progress retained `completed_at` in the isolated test; a later completion can keep the old date. Define reopening behavior, clear completion when leaving Done, and stamp each new completion. Keep lifecycle events in history.

## Reliability and usability

7. **Sharing is misleading.** The form offers sharing, but the Shared with Me tab is hidden and the backend does not expand access for the recipient (`app/main.py:520`). Either remove the field until supported or explicitly implement read-only sharing with permission tests. Do not silently grant editing rights.

8. **Save/delete failures are silent.** `app/static/index.html:792` and `:808` act only on success. Several fetch helpers parse JSON without checking HTTP status, and initialization errors can cause logout. Show actionable errors, preserve unsaved input, disable duplicate submissions, and distinguish expired login from temporary server failure.

9. **CSV imports can leave incorrect hierarchies.** Missing managers are reported after users are created, while self-management and cycles are not rejected. Arbitrary roles can include Admin and all imported users receive a shared initial password. Add a preview/validation phase, reject invalid hierarchies, make privileged roles explicit, and require first-login password changes. Prefer per-user temporary credentials. Include limits on file size and row count in the application itself.

10. **Time handling is ambiguous.** Timestamps are stored as naive UTC, while the browser parses them without an explicit UTC offset. The default due date uses a UTC date, which can differ from the local date before 05:30 in India. Return timezone-aware timestamps and derive the default due date from the user's local calendar date. Test around midnight in Asia/Calcutta.

11. **Audit writes are not atomic with several actions.** Task create/update commits inside CRUD, then the endpoint commits its activity log separately. An audit failure can return an error after the task has already saved. Use one transaction for each mutation and its audit record. Add conflict detection for concurrent edits to avoid silently overwriting a colleague's changes.

12. **Large teams will require query improvements.** The task endpoint returns every matching task with its history; pagination only slices the result in the browser. Hierarchy traversal queries one employee at a time and ORM relationships can cause additional queries. Add server-side pagination and totals, fetch history on demand, load related users efficiently, and index frequently filtered fields after measuring queries. A comment about 3,000 employees is not evidence of tested capacity.

13. **Operational recovery is incomplete in the repository.** No backup/restore automation or automated regression suite was found. SQLite-only schema patching does not provide PostgreSQL upgrade migrations. Add versioned migrations, daily database backups to a separate existing storage device, retention and a tested restore procedure. Configure automatic service restart, a database-aware health endpoint, and log retention. Ensure container logs are collected from stdout because the non-root image cannot normally create `/app/logs`.

14. **Authentication lifecycle needs strengthening.** Password changes and logout do not revoke existing JWTs; tokens last 24 hours. Add session records or a token version checked against the user, invalidate sessions on password change, and provide account disabling and password reset. Login attempt tracking is process-local, so restarts and additional workers affect enforcement; use a shared database-backed mechanism if needed.

## Free-only implementation sequence

1. Correct logout, HTML rendering, the dependency manifest, delegation filtering and lifecycle dates. Add regression tests for permissions and each confirmed bug.
2. Secure the existing internal deployment: environment secrets, least-privilege database access, HTTPS with the organization's certificate infrastructure, automatic startup/restart and recoverable backups. Avoid internet exposure by default.
3. Improve import validation, session revocation, visible error messages and timestamp handling.
4. Add server pagination, efficient queries and measured load testing before deciding whether more hardware is needed.
5. Add useful features: text search, assignee/category/priority filters, overdue highlighting, due-date sorting, in-app reminders, archive/restore, and task comments. These can all use the existing stack. Notifications should start inside the app; email can use an existing approved internal mail service if available.

## Free resources

- PostgreSQL is free and open source, including commercial use: https://www.postgresql.org/about/licence/
- PostgreSQL's included `pg_dump` is suitable for scheduled logical backups; restore to a separate database regularly to verify recoverability.
- pytest is free under the MIT license: https://pytest.org/en/latest/license.html
- Locust provides open-source load testing that can run on existing hardware: https://locust.io/
- Windows Task Scheduler and PowerShell can schedule backups and maintenance on the existing Windows installation. An existing Linux server can run the application as a system service. Neither plan requires a paid cloud account or a free-tier trial.

## Verification performed

- Parsed all top-level Python modules successfully.
- Installed-environment dependency consistency: `pip check` passed.
- Synthetic manager/reportee task: hierarchy view 1, delegated-by-me view 0, confirming the filter bug.
- Synthetic Done → In Progress transition: completion timestamp remained set, confirming the lifecycle bug.
- Cookie-only logout through FastAPI TestClient: HTTP 401, no cookie removal.
- Parsed the PostgreSQL requirement: entire version-suffixed string is a package name, with an empty version specifier.

These checks establish specific failures; they are not a full security audit or production readiness certification. The diagnosis did not read employee records or task contents from the existing database.
