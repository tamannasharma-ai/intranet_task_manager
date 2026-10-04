# Vercel demo

`main` is the disposable public demo. `local_setup` retains the local installation.
The demo never reads DATABASE_URL or tasks.db. It uses in-memory SQLite to keep
existing task, reporting, PDF, and account workflows available without provisioning
a database. Each process starts with 15 fictional employees, 73 fictional tasks,
and four categories. Every employee has personal to-do, in-progress, and completed
tasks. Each of the 14 reporting employees also has a manager assignment and a
shared assignment. Examples include all priorities, overdue work, work due today
and tomorrow, future deadlines, lifecycle history, and demo activity logs.
Due dates are relative to the instance startup date in India time.
Edits are temporary, can disappear between requests, and are not synchronized
between Vercel instances. This is not persistent team storage.

## Deploy

1. Commit and push these changes to main, then import the repository in Vercel.
2. Select the repository root and FastAPI framework. Keep build/output overrides empty.
3. Set SECRET_KEY to a long random secret (at least 32 random bytes), using the same
   value for all instances of the deployment. Enable it for Production and Preview.
   Vercel's VERCEL=1 enables secure cookies and requires this key.
4. Deploy and open /login. No PostgreSQL service or DATABASE_URL is needed.

The entry point is app/main.py. vercel.json selects FastAPI. Static assets use
module-relative paths, and Vercel logging goes to stdout. The .vercelignore file
excludes database files, local employee CSV, logs, and local runtime artifacts.
These exclusions do not remove sensitive files from existing Git history.

## Try the demo

Select any of the 15 accounts at /login. All use password `DemoPass123!`.
Administrator: `avery@example.com`. Reporting officers: `jordan@example.com`,
`riley@example.com`, and `casey@example.com`. The full fictional roster is in
app/demo_data.py. Do not upload real employee data to this demonstration.
AI features still need their separately configured provider credentials.

Use Jordan's account to explore delegation and team hierarchy, Taylor's account
for manager-assigned and shared work, and Avery's account for all-team reports
and activity logs. Personal work is available for every account. Task Summary,
PDF exports, and configured AI summaries use the same seeded tasks.

## Local verification

Run `.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v`.
Start with `.\.venv\Scripts\python.exe -B -m uvicorn app.main:app`.
A restart resets all changes. The existing start-app.cmd and Docker setup belong
to the local deployment workflow; use the command above for this demo.

Reference: https://vercel.com/docs/frameworks/backend/fastapi
