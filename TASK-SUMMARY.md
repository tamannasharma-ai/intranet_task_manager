# Task Summary and PDF download

Open **Task Summary** beside My Desk. The table shows each task's title, creator (Assigned by), assignee (Assigned to), current status, priority, due date and overdue flag. Use the employee, status and priority filters; **Pending** includes To Do and In Progress. Totals reflect the selected filters.

Click **Download PDF** to download `task-summary.pdf`. The PDF uses the same filters and includes all matching tasks, not just a page of cards. It is generated afresh when downloaded, so concurrent task updates can appear in the download. Reports include generation time in IST, page numbers and repeating column headings. Due dates are considered overdue after the due calendar day in India, unless the task is Done.

Access follows server-side permissions: employees see their own assignments and tasks they created; managers also see assignments throughout their reporting hierarchy; admins see all tasks. Filtering by an unrelated employee does not grant access. Both the summary and PDF endpoints require authentication.

PDF generation runs locally with the free ReportLab library. No external PDF service or subscription is used. Reports are generated in memory and served as downloads with no-store caching; the server does not save copies.

Validation: all 20 API regression tests and the frontend JavaScript checks passed. PDF tests cover authorization, filter parity, totals, empty reports and multi-page output. A synthetic two-page report was rendered and visually checked for spacing, text wrapping, repeated headings and footers.
