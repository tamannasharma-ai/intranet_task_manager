# Upload employee usernames and passwords

## Updating existing reporting managers

Sign in as an admin and choose **Manage Employees** in the top bar. Select an employee, choose a reporting manager (or **No reporting manager**), and click **Save Manager**. Self-reporting and direct or indirect reporting cycles are rejected. Each change is audited; existing tasks keep their assignees, while team workload visibility follows the updated hierarchy. Other users should refresh their dashboards to see the new reporting relationship.

Manager updates are separate from CSV import: existing accounts are still skipped during import.

## Importing new accounts

1. Start the updated backend with `start-app.cmd -Restart` and refresh the dashboard.
2. Sign in as an administrator and choose **Import Employees**.
3. Download the CSV template, fill it in and upload it. You can also use `employee-template.csv` from this folder.
4. Leave the optional default password blank when every row has its own password. Click **Import Employees** and check the result.

The smallest supported file has these headers:

```csv
username,password
```

Username is an employee email ending in `@thdc.co.in`. Plain usernames without an email domain are not supported. `email` can be used instead of `username`. Optional columns are `name`, `role` and `manager_email`. Without a name, the app uses the part of the email before `@`; without a role, it uses Junior Staff. A blank manager means no reporting officer.

Passwords must have at least 8 characters and at most 72 UTF-8 bytes. Password spaces are preserved. Quote values containing commas using ordinary CSV quoting. The uploaded CSV is not saved on the server; passwords are hashed before database storage and are not included in import results or activity records. Keep the source CSV private and use the organization's HTTPS deployment for network uploads.

Existing accounts are skipped, including their passwords and roles. This feature creates accounts; it does not reset existing passwords. Duplicate usernames within one upload, unknown managers, cyclic reporting relationships, malformed rows and invalid new-account passwords reject the entire upload. Manager rows may appear before or after their reportees.

Limits: UTF-8 CSV, 2 MB, 1,000 employee rows per upload. The previous `name,email,role,manager_email` format still works with an entered default password.

Validation: 13 API regression tests and the JavaScript checks passed, including distinct-password login, hashed storage, admin enforcement, unchanged existing passwords, invalid-file atomicity and legacy import compatibility. No actual employee CSV was uploaded during implementation.
