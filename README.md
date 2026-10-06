# TaskOrbit — Work Management Demo

**कार्याणां सुव्यवस्था, समूहस्य प्रगतिः।**

*Well-organized tasks, progress for the team.*

TaskOrbit is a browser-based task manager for personal work, reporting-officer assignments, team workload tracking, task history, filtered reports, and a read-only Groq AI assistant.

This README describes the current `main` branch. It is a **disposable Vercel demonstration**, with 15 fictional employees and 73 fictional tasks. The `local_setup` branch is intended to retain the original local installation; older Windows, Docker, and PostgreSQL instructions should not be treated as the deployment procedure for this branch.

Last updated: **October 4, 2026**.

## Contents

- [Demo storage and important limits](#demo-storage-and-important-limits)
- [Local startup](#local-startup)
- [Vercel deployment](#vercel-deployment)
- [Configuration](#configuration)
- [Demo accounts and scenarios](#demo-accounts-and-scenarios)
- [Task views and permissions](#task-views-and-permissions)
- [Task editing and lifecycle](#task-editing-and-lifecycle)
- [Employees and categories](#employees-and-categories)
- [Reports and PDF export](#reports-and-pdf-export)
- [Groq AI Console](#groq-ai-console)
- [Authentication and logs](#authentication-and-logs)
- [API reference](#api-reference)
- [Troubleshooting](#troubleshooting)
- [Verification and project layout](#verification-and-project-layout)

## Demo storage and important limits

The app uses SQLAlchemy with an **in-memory SQLite database**. It requires no external database service, creates no persistent database file, and intentionally ignores `DATABASE_URL`.

Each Python process initializes its own employees, categories, tasks, task histories, and activity records. Repeated seeding of the same populated store does not duplicate the sample data.

- Changes survive only while that process remains alive. Restarts, redeployments, and cold starts reset the data.
- Vercel can serve requests from different instances. A task created in one request may be missing from the next request if it reaches another instance.
- Task changes, imports, passwords, reporting relationships, categories, and audit records are all temporary.
- There is no durable backup, recovery, cross-instance synchronization, or shared transaction store.
- A lock serializes database-dependent requests within each process. Slow AI requests can delay other requests handled by that process.
- Rate limit counters are also per process and reset with it. They are not account-wide or deployment-wide limits.
- Task lists and reports load matching records without backend pagination. Browser pagination does not reduce the API response size.
- This branch has no validated production employee/concurrency capacity. The 1,000-row import allowance is an input limit, not a capacity guarantee.

Use fictional information only. Public demo credentials and the public account selector make this unsuitable for confidential employee work. Durable multi-user use requires a different storage and deployment design, not merely adding a `DATABASE_URL` variable.

## Local startup

The code uses Python 3.10+ syntax. Dependency compatibility must also be satisfied; this repository does not pin a Python runtime version. Node.js is only needed for the frontend regression script.

From the repository root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/login. Use a demo account below with password `DemoPass123!`.

Use one local worker for a consistent demonstration. Restarting resets the demo. The old `start-app.cmd`, Nginx, and Docker files describe the local installation workflow and are not required for this startup command.

The app reads process environment variables; it does not automatically load a root `.env` file. For example, set `$env:GROQ_API_KEY` in the launching PowerShell session or use the local configuration script and restart the launching process. Never commit actual credentials.

## Vercel deployment

1. Commit and push the desired `main` changes to your Git host.
2. Import the repository into Vercel with the repository root as the project root.
3. Select the **FastAPI** framework. Leave custom build and output-directory overrides empty.
4. Add `SECRET_KEY` in **Project Settings > Environment Variables** for Production and Preview. Use a long random value and retain the same value across instances of an environment.
5. Add the optional Groq configuration described below if you want AI features.
6. Deploy and visit `/login`. Test login, `/dashboard`, `/api/health`, and a PDF download.

Generate a signing secret locally:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Paste the output into Vercel's `SECRET_KEY` value. This is a session-signing key, separate from the Groq API key. Changing environment variables requires a new deployment.

`vercel.json` selects FastAPI and explicitly includes `app/static/**` in the function. The entry point is `app/main.py`. `.vercelignore` excludes local runtime files, database files, logs, and `Book1.csv`. Its `/index.html` rule excludes only the obsolete root page: **do not change it to `index.html`**, which would also exclude the dashboard under `app/static/`.

Ignore rules do not remove files from existing Git history. The root `index.html` is not the live dashboard; edit `app/static/index.html` instead.

References: [Vercel FastAPI support](https://vercel.com/docs/frameworks/backend/fastapi) and [environment variables](https://vercel.com/docs/environment-variables/managing-environment-variables).

## Configuration

- **`SECRET_KEY`**: required whenever `VERCEL=1` or `APP_ENV=production`. Missing configuration stops app import. Local development otherwise generates a temporary key. JWTs use HS256 and expire after 24 hours.
- **`VERCEL`**: platform indicator. `1` enables production security behavior and defaults logging to stdout. Normally supplied by Vercel.
- **`APP_ENV`**: defaults to `development`; `production` enables secure cookies and requires the signing secret. It does not turn this demo into persistent storage.
- **`SECURE_COOKIES`**: `true` enables HTTPS-only cookies locally; Vercel/production enables them automatically. Setting this on an HTTP-only local demo can prevent cookie-based dashboard access.
- **`ALLOWED_ORIGINS`**: optional comma-separated CORS origins. Defaults to `http://127.0.0.1:8000,http://localhost:8000`. Same-origin browser requests do not require adding the Vercel hostname here.
- **`GROQ_API_KEY`**: optional for the rest of the app, required for AI. Stored only in the server environment and never returned by the configuration API.
- **`GROQ_FREE_TIER_CONFIRMED`**: set to `true` only after confirming the account uses Groq's Free Plan. Whitespace and letter case are normalized.
- **`LOG_LEVEL`**: defaults to `INFO`.
- **`LOG_FILE`**: optional local log destination. Defaults to `logs/continuum.log` locally and no file on Vercel. An empty value disables file logging.
- **`DATABASE_URL`**: intentionally unused on this branch.

The Groq model is currently a code constant, `qwen/qwen3.8-27b`, in `app/ai_console.py`. A `GROQ_MODEL` environment variable is not implemented. Bootstrap-admin variables from older local documentation are not used by the demo seed.

## Demo accounts and scenarios

All accounts use **`DemoPass123!`**. Their addresses are fictional `example.com` addresses. Select a person on the login page to fill their email.

### Administrator

- Ananya Sharma — `ananya@example.com` — Admin; no manager.

### Engineering team

- Arjun Mehta — `arjun@example.com` — Reporting Officer; reports to Ananya.
- Neha Verma — `neha@example.com` — Junior Engineer; reports to Arjun.
- Vikram Rao — `vikram@example.com` — Junior Engineer; reports to Arjun.
- Ishaan Gupta — `ishaan@example.com` — Project Analyst; reports to Arjun.
- Pooja Desai — `pooja@example.com` — Junior Staff; reports to Arjun.

### Operations team

- Kavya Nair — `kavya@example.com` — Reporting Officer; reports to Ananya.
- Aditya Menon — `aditya@example.com` — Operations Officer; reports to Kavya.
- Sneha Kulkarni — `sneha@example.com` — Junior Ops Officer; reports to Kavya.
- Kunal Joshi — `kunal@example.com` — Project Analyst; reports to Kavya.
- Divya Reddy — `divya@example.com` — Junior Staff; reports to Kavya.

### Support team

- Rohan Iyer — `rohan@example.com` — Reporting Officer; reports to Ananya.
- Nitin Shah — `nitin@example.com` — Finance Officer; reports to Rohan.
- Meera Singh — `meera@example.com` — HR Coordinator; reports to Rohan.
- Sanjay Das — `sanjay@example.com` — Junior Staff; reports to Rohan.

### What is preloaded

Every employee has three personal tasks: a high-priority review due today, a medium-priority overdue report in progress, and a completed low-priority email update. That provides 45 personal tasks.

Each of the 14 employees with a manager also has an approval assignment and a shared feedback assignment, providing another 28 tasks. Approval statuses vary. Shared examples are assigned and shared to the same recipient, matching the API's visibility rule.

The four categories are **Send email**, **Take approval**, **Prepare report**, and **Review document**. Tasks include fictional summaries, creation histories, lifecycle transitions, and corresponding activity events. Due dates are relative to instance startup in India time; timestamps are stored in UTC. Dates are not reseeded each midnight on an existing instance.

Try Arjun for delegation and team visibility, Neha for assigned work and editing, and Ananya for all-user reports and employee administration. The administrator's activity log is available through the API rather than a dedicated dashboard page.

## Task views and permissions

**My Day** is the default view: your unfinished tasks grouped as Overdue, Due Today, and Upcoming, using India time. Cards offer Start, Complete, Reschedule, and Archive.

**My Desk** shows tasks created by or assigned to the signed-in employee across To Do, In Progress, Blocked, and Done. Completed work appears alongside pending work. Even the administrator's desk is personal in scope.

**Personal Tasks** shows tasks both created by and assigned to the current employee, including completed work.

**Assigned by RO** shows tasks assigned to the current employee by their current manager. RO means reporting officer. Changing a manager can change which existing tasks appear here.

**Delegated by Me** shows tasks created by the current employee and assigned within their current reporting hierarchy. The dashboard displays this tab for non-admin employees who have direct reports. The endpoint also supports administrators, although their UI hides this tab.

**Team Hierarchy** includes tasks assigned to direct and indirect reports. Administrators see all tasks through the corresponding **All Users Workload** view. A role label alone does not create reports: hierarchy relationships determine reporting access.

**Shared with Me** lists tasks where you are explicitly added as a collaborator or viewer. The legacy shared recipient is treated as a read-only viewer. Use Details > Participants to manage explicit roles.

**Archive** and **Trash** retain tasks, comments and history. Only the owner can archive, move to Trash, or restore a task. These views are excluded from active boards, reports and AI summaries.

### Assignment and modification rules

- A user may assign a task to themselves or a direct report only. This applies to administrators too.
- Managers can view descendant workload but cannot assign directly to an indirect report under this rule.
- The current assignee is the owner and can edit, reassign, archive, delete to Trash, and restore. Collaborators can update status, the blocked reason and checklist, and post comments. Viewers can read only. The creator or owner can manage participants. Reporting managers and administrators retain visibility and commenting rights; these roles do not grant owner edit rights.
- Reassignment must also satisfy the self/direct-report rule for the user making the change.
- The sharing field must reference an existing user. Category references must exist.
- Access is checked by the API; hiding a button is not the only enforcement.

### Board behavior

The board groups tasks into To Do, In Progress, Blocked, and Done. Pending cards are sorted by earliest due date (overdue first), then priority, then ID. Done cards show the most recent completion first; missing completion dates follow dated tasks. Each column has independent pagination, with nine tasks per column by default. The page-size selector offers 6, 9, or 15 tasks per column. It applies to each column and resets all four to page one; changing views also resets the pages. Pagination happens in the browser after fetching the matching list. KPI counts cover the entire selected view, and column badges show all tasks in that status regardless of the current page.

Cards show priorities, due-date labels, category, and history. Browser due-date labels use the browser's local date; server reports use India time, so these can differ near midnight for users in other timezones. The notification bell polls every minute while the page is visible, showing assignments, comments, status changes and daily due reminders. It is in-app only; no email or operating-system push service is used.

## Task editing and lifecycle

Create or edit a task using a title, summary, due date, assignee, priority, status, optional category, and optional shared recipient.

- Title: 1–200 characters.
- Summary: optional; no explicit maximum in the task API schema. AI uses only a truncated excerpt.
- Due date: required calendar date; past dates are allowed.
- Priority: exactly `Low`, `Medium`, or `High`.
- Status: `todo`, `inprogress`, `blocked`, or `done`. Blocked tasks require a reason of up to 1,000 characters.
- Repeat: none, daily, weekly or monthly. Completion creates one next occurrence from the prior due date, preserving month-end scheduling and resetting checklist progress.
- Checklist: up to 50 steps, each with 1–300 characters.
- Participants: up to 30 explicit collaborators/viewers. Owner and creator already have access.
- One assignee, one optional shared recipient, and one optional category per task.

Creation records the creator and timestamp. Starting work records a start time; completing it records completion. Reopening clears completion but retains a previously recorded start time. Creating a task directly as Done may leave its start time empty. These timestamps are lifecycle records, not an active time tracker or timesheet.

The history dialog displays creation/start/completion timestamps and recorded changes. Edits to assignment, priority, category, due date, title, summary, sharing, and status are recorded. Deleting moves a task to Trash and preserves history and comments. Restore returns it to active work. All of this remains temporary for the lifetime of the demo process.

## Employees and categories

### Reporting relationships

Administrators can select an employee and change or remove their manager. Unknown users, self-reporting, and circular reporting chains are rejected. Relationships immediately affect hierarchy-based permissions on that instance. There is no separate employee creation form, employee deletion endpoint, or general role-editing endpoint.

### Employee CSV import

Administrators can download a CSV template and upload a UTF-8 CSV file.

- File extension must be `.csv`; maximum size is 2 MiB (2 × 1,024 × 1,024 bytes).
- At most 1,000 data rows per upload; the header is not counted.
- Supply `username` or `email`. If both are supplied, they must match.
- Supply a `password` column or the form's default password.
- Optional columns: `name`, `role`, `manager_email`.
- Header names are trimmed and normalized to lowercase; duplicate headers are rejected.
- New employee usernames must end in **`@thdc.co.in`**. This legacy import restriction remains even though seeded demo accounts use `@example.com`.
- Passwords need at least eight characters and at most 72 UTF-8 bytes. Password whitespace is preserved.
- Names must be 1–100 characters; roles 1–50 characters. The default name is the email prefix and the default role is `Junior Staff`.
- Managers must already exist or be included in the same import. Cycles among imported reporting links are rejected.
- Existing account emails are skipped, not updated. Duplicate usernames within the CSV are errors.
- Validation errors reject the import before account creation; at most the first 20 error messages are returned. Database conflicts roll back the import.
- Imported accounts and hierarchy changes disappear when the instance resets.

Use only fictional test records. The seeded `example.com` roster is not directly re-importable under the legacy domain restriction.

### Categories

Any signed-in employee can create a category. Names are 1–80 characters; whitespace is normalized, and case-insensitive matches reuse the existing category. Tasks may be uncategorized. Category rename/delete endpoints are not implemented.

## Reports and PDF export

Task Summary places a filter directly beneath each of its seven column headings:

- **Task:** search a title or task ID, such as `report` or `#12`. Matching is literal, case-insensitive substring matching; `%` and `_` are not wildcards.
- **Assigned by:** search the creator's name, case-insensitively. This is the task creator, who is not necessarily the employee's current manager.
- **Assigned to:** select an employee from the authorized report's employee list.
- **Status:** All, Pending, To Do, In Progress, or Done. Pending combines To Do and In Progress.
- **Priority:** All, Low, Medium, or High.
- **Due date:** choose an optional From date, To date, or both. Both boundaries are inclusive.
- **Overdue:** All, Yes, or No. No includes completed tasks and pending tasks not yet overdue.

All active filters combine with **AND**. Text inputs allow up to 200 characters and refresh after a 300 ms typing pause. Selection and date changes refresh immediately. These controls filter on the server; the response totals and downloaded PDF use the same parameters.

Use **Clear filters** to reset all seven columns to the full authorized report. Employee choices remain available when other filters yield no rows. Empty results display “No tasks match these filters” with zero totals. Invalid dates, reversed date ranges, invalid overdue values, and overlong text are rejected.

For example, select an employee, choose Pending and High, and set Overdue to Yes to see that employee's high-priority overdue work. Add an Assigned by name to narrow it to a particular creator. Download PDF exports that same selection and includes the active filters in its heading.

Summary filters are separate from board tabs and AI Console filters. They are held in the current browser page, not saved as reusable report presets.

Administrators can report on all tasks. Other users can report on tasks assigned to themselves or descendants, plus tasks they created. This is deliberately broader than My Desk's creator/assignee scope. A filter never expands authorization.

Reports show task identifiers, titles, creator, assignee, status, priority, due date, and overdue flags. Totals count all matching tasks. Overdue means unfinished with a due date before today's date in `Asia/Kolkata`. Completed tasks are not overdue.

Download PDF produces a factual landscape A4 report with the selected filters, totals, task rows, repeated table headings, page numbers, and an India-time generation timestamp. It is generated in memory and is separate from AI-generated text. There is no report row cap or export pagination API; very large datasets can affect memory, latency, and function execution limits. Standard PDF fonts may not cover every writing system.

## Groq AI Console

The console answers questions and generates summaries from an authorized snapshot of tasks. It can discuss progress, delegation, overdue work, and suggested next steps, citing task IDs. Employee and status filters narrow the supplied data; AI-specific priority filtering is not implemented.

### Setup

On Vercel, add `GROQ_API_KEY` and `GROQ_FREE_TIER_CONFIRMED=true` in project environment variables for Production and Preview, then redeploy. Set the confirmation only after checking the account's plan. The configuration message identifies missing settings.

For the local Windows installation, `configure-ai.cmd` invokes `scripts/configure-groq.ps1`; restart the app in a process that receives the new environment. Do not try to run that Windows script on Vercel.

### Application limits

- Five requests per user per rolling 60 seconds per process. Attempts admitted by this limiter count even if the provider subsequently fails.
- Questions: 1–2,000 characters; blank questions after trimming are rejected.
- At most 30 task details, ordered by due date and ID.
- At most 12,000 UTF-8 bytes across serialized task-detail objects; this is not an exact token count or a cap on the full HTTP body.
- At most 400 description characters per included task.
- Full matching totals are still supplied when task details are partial.
- Output request limit: 1,500 completion tokens.
- HTTP timeout settings: 45 seconds generally and 10 seconds for connecting; these are client operation timeouts, not a guarantee of total end-to-end duration.
- No automatic provider retry, alternative model, or paid fallback.
- Questions are independent; previous conversation turns are not sent back.
- No visible matching tasks returns a local message without calling Groq, after configuration/rate checks.

The UI displays the number of details supplied versus total matching tasks. With partial context, the model cannot reliably provide an exhaustive task-by-task or employee-by-employee breakdown. Narrow the filters for detail and use the factual report for a complete list.

### Provider limits and observed failure

Groq limits vary by account, model, and service tier. The app cannot verify billing or guarantee zero charges; `GROQ_FREE_TIER_CONFIRMED` is an administrator attestation.

During debugging on October 4, 2026, a full demo request was rejected with HTTP 413: 7,502 requested input tokens exceeded that account's 7,000 input-tokens-per-minute limit. This is an observed account limit, not a universal Groq quota. The reduced request succeeded with 30 details and totals for all 73 tasks. Accumulated requests can still hit provider limits.

The current model and reasoning parameters are configured in `app/ai_console.py`. Check [Groq model documentation](https://console.groq.com/docs/model/qwen/qwen3.8-27b) and [account rate limits](https://console.groq.com/docs/rate-limits) before changing them.

### Data and capabilities

Submitting a question sends the question, authorized task titles/descriptions, creator/assignee names, statuses, priorities, dates, identifiers, and aggregate totals to Groq. Employee email fields, password hashes, and audit logs are not included as structured context. However, anything a user types into task text or a question can be transmitted as part of that text.

Opening the console alone does not send task data to Groq. The assistant has no write tools, SQL access, file access, or ability to create, edit, assign, or delete tasks. Responses are rendered as plain text. Suggestions can be incorrect and are not workflow actions.

## Authentication and logs

Login normalizes the email and verifies a bcrypt password hash. Tokens expire after 24 hours. The browser stores the bearer token and user display details in local storage; an HttpOnly, SameSite=Lax cookie controls page access. Production cookies are Secure. Local storage tokens remain accessible to JavaScript, so this is not an HttpOnly-only session design.

After five failed attempts within 15 minutes for an IP/email pair, further attempts on that process are throttled. Successful login clears that pair's recorded attempts. There is no shared rate-limit backend.

Password changes require the current password and a different replacement. The schema accepts 8–128 characters, but bcrypt has a 72-byte effective password limit; stay within 72 UTF-8 bytes. This mismatch is a known limitation. There is no password-reset email, MFA, SSO, or self-registration.

Logout clears browser state/cookie but does not maintain a server-side token revocation list. An issued token can remain valid until expiry; changing a password does not invalidate existing tokens automatically.

HTTP responses include request IDs and security headers; production adds HSTS. Request logs record method, path, status, duration, and client IP. Local logs rotate at 10 MiB with five backups; Vercel defaults to stdout.

Activity records cover task/category changes, login successes/failures/throttling, logout, password changes, imports, and manager changes. They can contain actor email, request metadata, IP, and user agent. `GET /api/admin/activity-logs` is admin-only, defaults to 100 newest records, and accepts `limit` from 1 to 500. There is no pagination cursor or dedicated audit-log dashboard. All these records are ephemeral in the demo database.

## API reference

Interactive schemas are available at `/docs`; the machine-readable schema is `/openapi.json`. API operations below require a bearer token unless marked public. Page routes instead check the login cookie.

### Pages and assets

- `GET /`: redirects based on the session cookie.
- `GET /login` and `/login.html`: public login page.
- `GET /dashboard` and `/dashboard.html`: protected dashboard page.
- `GET /vendor/...`: bundled styles, icons, fonts, and scripts.

### Health and authentication

- `GET /api/health`: public database connectivity check; returns 503 on failure. It does not verify Groq connectivity.
- `GET /api/auth/users`: public fictional account directory; excludes password hashes.
- `POST /api/auth/login`: public form submission using `username` and `password`.
- `POST /api/auth/logout`: clears cookie; records logout when a valid token is supplied.
- `POST /api/users/me/change-password`: `old_password`, `new_password`.

### Employees and categories

- `GET /api/users`: directory of users for signed-in users.
- `POST /api/users/import`: admin multipart upload with `file` and optional `default_password`.
- `PUT /api/users/{user_id}/manager`: admin update with `manager_id`, or null to remove the manager.
- `GET /api/categories`: category list.
- `POST /api/categories`: create/reuse a category by `name`.

### Tasks, reporting, and AI

- `GET /api/tasks?filter_type=all`: supported filters are `all`, `personal`, `assigned-by-ro`, `delegated-by-me`, `team-hierarchy`, and `shared`.
- `POST /api/tasks`: create task; fields and assignment restrictions described above.
- `PUT /api/tasks/{task_id}`: partial task update by its assignee.
- `DELETE /api/tasks/{task_id}`: move to Trash by its owner.
- `GET /api/tasks/{task_id}`: permission-scoped details.
- `PUT /api/tasks/{task_id}/collaboration`: creator/owner manages participants.
- `POST /api/tasks/{task_id}/archive` and `/restore`: owner-only recovery workflows.
- `GET /api/notifications`: latest 100 visible notifications and unread count.
- `POST /api/notifications/read-all` or `/{notification_id}/read`: mark your notifications read.
- See [VOICE-COMMENTS.md](VOICE-COMMENTS.md) for comments and dictation.
- `GET /api/reports/tasks`: optional `assignee_id`, `status`, `priority`, `task_text`, `creator_text`, `due_from`, `due_to`, and `overdue` (`all`, `yes`, `no`) filters.
- `GET /api/reports/tasks.pdf`: same filters, returns PDF bytes.
- `GET /api/ai/config`: safe configuration flags, model, and setup message; no key value.
- `POST /api/ai/chat`: `question`, `mode` (`question` or `summary`), optional `assignee_id`, and `status`.
- `GET /api/admin/activity-logs?limit=100`: admin activity records.

No attachments, subtasks, recurring tasks, email delivery, reminders, external calendar synchronization, or background job queue are implemented. The “Send email” category is a task label, not an email-sending integration.

## Troubleshooting

### Could not import app/main.py

Read the final traceback line. If it says `SECRET_KEY is required when APP_ENV=production`, add `SECRET_KEY` for the environment being deployed and redeploy. The same guard also applies when Vercel sets `VERCEL=1`.

### Dashboard HTML missing

For `File at path /var/task/app/static/index.html does not exist`, verify that file is committed, `.vercelignore` excludes `/index.html` rather than every `index.html`, and `vercel.json` includes `app/static/**`. Push the corrected configuration and redeploy.

### AI setup needed

Check both Groq variables in the deployed environment. Setting them on Windows does not update Vercel. The old message about running a PowerShell script on the server belonged to local setup; deploy the current code to see Vercel-specific instructions.

### AI request too large or rate limited

HTTP 413 means the provider rejected the request size; filter by employee/status. HTTP 429 means the application or provider limiter was reached; wait before retrying. Requests share the provider account's quotas even when different app users submit them.

Provider 401/403 indicates key/access problems and is surfaced as an app 503. Provider 400 or 404 produces an app 502 with a settings/model message. Timeouts return 504; malformed responses or network errors return 502. The app deliberately does not expose raw provider error bodies containing account details.

### Task missing or action forbidden

Confirm the active view, current assignee, and current reporting relationships. Completed tasks are included on My Desk and appear in its independently paginated Done column. A manager cannot edit another person's assignment merely because they created it. An administrator is also subject to assignee-only modification rules. On Vercel, a reset or different instance can independently explain missing changes.

### Dates or counts differ

Board KPIs cover a selected view, column badges cover all tasks in their status, and reports cover their own authorized filter scope. Browser date labels and India-time report calculations can differ near midnight. Partial AI context does not mean the full report totals are partial.

## Verification and project layout

Install development dependencies and run the checks from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
node tests/frontend-regressions.cjs
```

Latest application verification on October 4, 2026: **27 Python tests passed**, and the frontend regression checks passed. A separate live Groq check successfully summarized the fictional workload with 30 task details and totals for all 73 tasks. Unit tests mock provider responses; they do not require a live key or prove every Vercel deployment succeeds.

Coverage includes task visibility/modification, hierarchy updates, import validation, authentication-related behavior, combined summary-column filters, matching PDF results, invalid date ranges, literal text searches, report/PDF scope, AI context boundaries and provider failures, demo seeding idempotency, login for all 15 accounts, and a fresh Vercel-style process. Frontend checks cover independent column pagination, deadline/completion ordering, total badges, page clamping after data changes, empty columns, safe rendering, and logout. Test databases are in-memory and do not connect to a configured external database.

### Search, prerequisites, and mobile navigation

Search matches titles, descriptions, comments, owners, creators, categories and exact task IDs (for example `#4`). Choose Active, Archive or Trash; results always respect your task access. `%` and `_` are literal characters, not wildcards.

Open a task's **Details → Prerequisite tasks** to find and add a prerequisite. Owners and creators can manage links; collaborators can update progress but cannot change dependencies. Unfinished or deleted prerequisites prevent starting or completing a task. Circular links and self-dependencies are rejected. Completed archived prerequisites count as finished. Restricted prerequisites hide their identity. Recurring tasks begin each new occurrence without dependency links; reopening an upstream task does not automatically change downstream statuses.

On phones, use the View selector to change task views. Search, single-column task cards, larger touch targets and scrollable dialogs adapt to narrow screens. Account controls remain available below the workspace. Storage remains temporary; no approval workflow is added.

Key files:

- `app/main.py`: FastAPI routes, access checks, middleware, seeding, and pages.
- `app/database.py`: process-local in-memory store and request serialization.
- `app/demo_data.py`: fictional accounts, task scenarios, and initial histories.
- `app/models.py` / `app/schemas.py`: ORM entities and API validation.
- `app/crud.py`: task mutations and lifecycle history.
- `app/auth.py`: password hashing and JWT handling.
- `app/employee_import.py`: CSV validation and hierarchy checks.
- `app/task_reports.py`: scoped report data and PDF generation.
- `app/ai_console.py`: Groq payloads, bounds, configuration, and error handling.
- `app/logging_config.py`: JSON request/event logging.
- `app/static/login.html` / `app/static/index.html`: active browser UI.
- `app/static/vendor/`: local frontend assets.
- `vercel.json` / `.vercelignore`: deployment configuration and exclusions.
- `tests/`: Python and frontend regression checks.

Additional background: [Vercel demo notes](VERCEL.md), [AI Console](AI-CONSOLE.md), [employee import](EMPLOYEE-IMPORT.md), and [task summary](TASK-SUMMARY.md). Older local deployment documents can describe behavior that differs from this demo branch; the current code and this README describe the active demo.
