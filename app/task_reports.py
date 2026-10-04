"""Permission-scoped summary data and downloadable PDF reports."""
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from xml.sax.saxutils import escape

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from app.models import Task, User

STATUS_LABELS = {"todo": "To Do", "inprogress": "In Progress", "done": "Done"}
IST = timezone(timedelta(hours=5, minutes=30))


def task_summary(db, user, reportee_ids, assignee_id=None, status="all", priority="all",
                 task_text="", creator_text="", due_from="", due_to="", overdue="all"):
    if status not in {"all", "pending", *STATUS_LABELS}:
        raise HTTPException(400, "Invalid status filter")
    if priority not in {"all", "Low", "Medium", "High"}:
        raise HTTPException(400, "Invalid priority filter")
    if overdue not in {"all", "yes", "no"}:
        raise HTTPException(400, "Invalid overdue filter")
    if len(task_text) > 200 or len(creator_text) > 200:
        raise HTTPException(400, "Text filters must be at most 200 characters")
    try:
        due_from = date.fromisoformat(due_from).isoformat() if due_from else ""
        due_to = date.fromisoformat(due_to).isoformat() if due_to else ""
    except ValueError:
        raise HTTPException(400, "Date filters must be valid ISO dates")
    if due_from and due_to and due_from > due_to:
        raise HTTPException(400, "From date must not be after To date")
    query = db.query(Task).options(selectinload(Task.creator), selectinload(Task.assignee))
    if user.role != "Admin":
        query = query.filter(or_(Task.assignee_id.in_([user.id, *reportee_ids]), Task.creator_id == user.id))
    if assignee_id is not None:
        query = query.filter(Task.assignee_id == assignee_id)
    if status == "pending":
        query = query.filter(Task.status.in_(["todo", "inprogress"]))
    elif status != "all":
        query = query.filter(Task.status == status)
    if priority != "all":
        query = query.filter(Task.priority == priority)
    today = datetime.now(IST).date().isoformat()
    rows = [{"id": task.id, "title": task.title,
             "creator": task.creator.name, "assignee": task.assignee.name,
             "assignee_id": task.assignee_id, "status": task.status,
             "priority": task.priority, "due_date": task.due_date,
             "overdue": task.status != "done" and task.due_date < today}
            for task in query.order_by(Task.due_date, Task.id).all()]
    # Filter only the already-authorized rows; matching is literal, not SQL wildcard search.
    rows = [row for row in rows
            if (not task_text.strip() or task_text.strip().casefold() in f"#{row['id']} {row['title']}".casefold())
            and (not creator_text.strip() or creator_text.strip().casefold() in row["creator"].casefold())
            and (not due_from or row["due_date"] >= due_from)
            and (not due_to or row["due_date"] <= due_to)
            and (overdue == "all" or row["overdue"] == (overdue == "yes"))]
    # Employee choices remain stable when the status/priority filters change.
    people = db.query(User).join(Task, Task.assignee_id == User.id)
    if user.role != "Admin":
        people = people.filter(or_(Task.assignee_id.in_([user.id, *reportee_ids]), Task.creator_id == user.id))
    return {"tasks": rows,
            "employees": [{"id": person.id, "name": person.name, "email": person.email}
                          for person in people.distinct().order_by(User.name).all()],
            "totals": {"total": len(rows), "pending": sum(row["status"] != "done" for row in rows),
                       "done": sum(row["status"] == "done" for row in rows),
                       "overdue": sum(row["overdue"] for row in rows)},
            "generated_at": datetime.now(IST).isoformat()}


def summary_pdf(summary, requested_by, filters):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle

    stream = BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=landscape(A4), leftMargin=32, rightMargin=32,
                            topMargin=32, bottomMargin=34, title="TaskOrbit Task Summary")
    styles = getSampleStyleSheet()
    cell = ParagraphStyle("ReportCell", fontName="Helvetica", fontSize=8, leading=11, wordWrap="CJK")
    def paragraph(value):
        return Paragraph(escape(str(value)), cell)
    totals = summary["totals"]
    content = [Paragraph("TaskOrbit | Task Summary", styles["Title"]),
               Paragraph(escape(f"Prepared for {requested_by} | {summary['generated_at'][:19].replace('T', ' ')} IST"), styles["Normal"]),
               Spacer(1, 7), Paragraph(escape(filters), styles["Normal"]), Spacer(1, 9),
               Paragraph(f"Total: {totals['total']} &nbsp; Pending: {totals['pending']} &nbsp; Completed: {totals['done']} &nbsp; Overdue: {totals['overdue']}", styles["Normal"]), Spacer(1, 14)]
    if not summary["tasks"]:
        content.append(Paragraph("No tasks match these filters.", styles["Normal"]))
    else:
        data = [[paragraph(label) for label in ["Task", "Assigned by", "Assigned to", "Status", "Priority", "Due date", "Overdue"]]]
        for row in summary["tasks"]:
            data.append([paragraph(value) for value in [f"#{row['id']} {row['title']}", row["creator"], row["assignee"],
                         STATUS_LABELS[row["status"]], row["priority"], row["due_date"], "Yes" if row["overdue"] else "No"]])
        table = LongTable(data, colWidths=[245, 125, 125, 80, 60, 85, 57], repeatRows=1, splitInRow=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#94a3b8")),
        ]))
        content.append(table)
    def footer(canvas, document):
        canvas.setFont("Helvetica", 8)
        canvas.drawString(32, 18, "TaskOrbit - task status at time of download | Dates: Asia/Kolkata")
        canvas.drawRightString(810, 18, f"Page {document.page}")
    doc.build(content, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
