"""Validate employee CSVs before creating accounts. Never return passwords."""
import csv
import io

from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException


def parse_employees(content: bytes, default_password: str, existing: dict):
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), strict=True)
        headers = [column.strip().lower() for column in (reader.fieldnames or [])]
        if len(set(headers)) != len(headers) or not ({"email", "username"} & set(headers)):
            raise HTTPException(400, "CSV needs a username or email column and unique column names")
        if "password" not in headers and not default_password:
            raise HTTPException(400, "Add a password column or enter a default password")
        reader.fieldnames = headers
        rows, skipped, errors, seen = [], [], [], set()
        for number, raw in enumerate(reader, start=2):
            if number > 1001:
                raise HTTPException(400, "Upload at most 1,000 employees at a time")
            if None in raw or any(value is None for value in raw.values()):
                errors.append(f"Row {number}: number of values does not match the headers")
                continue
            email = (raw.get("email") or raw.get("username") or "").strip().lower()
            if raw.get("email") and raw.get("username") and raw["email"].strip().lower() != raw["username"].strip().lower():
                errors.append(f"Row {number}: email and username must match")
                continue
            try:
                email = validate_email(email, check_deliverability=False).normalized.lower()
            except EmailNotValidError:
                errors.append(f"Row {number}: username must be a valid email address")
                continue
            if not email.endswith("@thdc.co.in"):
                errors.append(f"Row {number}: username must use @thdc.co.in")
                continue
            if email in seen:
                errors.append(f"Row {number}: duplicate username")
                continue
            seen.add(email)
            if email in existing:
                skipped.append(email)
                continue
            # Preserve password whitespace exactly; bcrypt has a 72-byte limit.
            password = raw.get("password") or default_password
            if len(password) < 8 or len(password.encode("utf-8")) > 72:
                errors.append(f"Row {number}: password needs at least 8 characters and at most 72 UTF-8 bytes")
                continue
            name = (raw.get("name") or email.split("@")[0]).strip()
            role = (raw.get("role") or "Junior Staff").strip()
            manager_email = (raw.get("manager_email") or "").strip().lower()
            if not name or len(name) > 100 or not role or len(role) > 50:
                errors.append(f"Row {number}: name must be 1–100 characters and role 1–50 characters")
                continue
            rows.append(dict(number=number, name=name, email=email, password=password, role=role, manager_email=manager_email))
        if not seen and not errors:
            errors.append("CSV contains no employee rows")
        all_emails = set(existing) | {row["email"] for row in rows}
        for row in rows:
            if row["manager_email"] and row["manager_email"] not in all_emails:
                errors.append(f"Row {row['number']}: manager must exist or be included in this CSV")
        links = {row["email"]: row["manager_email"] for row in rows}
        for row in rows:
            visited, email = set(), row["email"]
            while email in links:
                if email in visited:
                    errors.append(f"Row {row['number']}: reporting hierarchy contains a cycle")
                    break
                visited.add(email)
                email = links[email]
        if errors:
            raise HTTPException(400, "No accounts imported. " + "; ".join(errors[:20]))
        return rows, skipped
    except (UnicodeDecodeError, csv.Error):
        raise HTTPException(400, "CSV must be valid UTF-8 CSV")
