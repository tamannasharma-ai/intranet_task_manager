# Starting TaskOrbit on Windows

Double-click `start-app.cmd` to start the application. Open http://127.0.0.1 after it reports **Application is ready**. Service processes run in hidden windows; the launcher itself displays progress and errors.

From a terminal in this project:

```powershell
.\start-app.cmd
.\start-app.cmd -Restart
.\start-app.cmd -CheckOnly
```

- Normal startup reuses a healthy backend without restarting it.
- `-Restart` stops only the saved backend PID after verifying the executable belongs to this project's virtual environment and its command line runs this app on port 8000. It then starts the new code. Nginx is reused. If the PID is missing or does not match, an occupied port is left untouched and the launcher reports what to do.
- `-CheckOnly` checks for Python and validates the Nginx configuration without starting services or connecting to the database. It creates necessary log/runtime/temporary directories.
- Optional `-TimeoutSeconds 60` increases the health-check wait from 30 seconds.

The launcher verifies `/api/health` directly and through Nginx before reporting readiness. That endpoint executes a database query; a failed query returns HTTP 503 without exposing connection details. An old backend without this endpoint must be restarted.

## Errors

Startup failure returns exit code 1. The CMD launcher pauses so double-click users can read the error (except when `-CheckOnly` is the first argument).

- Missing Python: restore `.venv` and install `requirements.txt`.
- Missing Nginx: set `NGINX_EXE` to the full executable path.
- Nginx configuration failure: read `logs/nginx-check-error.log`.
- Backend failure: check PostgreSQL and database connection settings, then `logs/uvicorn-error.log`.
- Proxy failure: check port 80 conflicts and `logs/nginx-error.log`.

Failed health checks do not automatically kill processes. Resolve the error and use `-Restart` if a backend remains running. An unrelated process occupying a port is never automatically terminated.

Validation: configuration-only startup passed against the installed Nginx; eight API regression tests passed including healthy/unavailable database responses. Full service startup and restart were not exercised during this launcher update.
