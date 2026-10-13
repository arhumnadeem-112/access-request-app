"""
Reset the database and fill it with made-up demo data.

Run it with:   python seed.py

WARNING: this deletes everything in access.db and starts over. That's handy
when you want a clean slate after testing.
"""
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

import db

# Every demo user gets this password. (Fine for a demo, never for real use.)
DEMO_PASSWORD = "demo123"

# (username, full name, role, username of their manager)
# The admin has no manager. Managers report to the admin, so the admin approves
# managers' own requests. Employees report to one of the two managers.
USERS = [
    ("admin",    "Alex Morgan",   "admin",    None),
    ("pshah",    "Priya Shah",    "manager",  "admin"),
    ("mlee",     "Marcus Lee",    "manager",  "admin"),
    ("jkim",     "Jordan Kim",    "employee", "pshah"),
    ("srivera",  "Sam Rivera",    "employee", "pshah"),
    ("tbrooks",  "Taylor Brooks", "employee", "pshah"),
    ("cnguyen",  "Casey Nguyen",  "employee", "mlee"),
    ("rpatel",   "Riley Patel",   "employee", "mlee"),
]

SYSTEMS = [
    ("Finance Reporting", "Budgets, forecasts and monthly financial reports"),
    ("HR Database",       "Employee records, org chart and onboarding data"),
    ("CRM",               "Customer accounts, contacts and sales pipeline"),
    ("Code Repository",   "Source code and version control for internal tools"),
    ("Payroll",           "Salaries, tax withholding and pay runs"),
]

# (requester, system, reason, status, days ago created, hours until decision, comment)
# For Pending requests, "hours until decision" and "comment" are None.
# Whoever decides a request is always the requester's manager.
REQUESTS = [
    ("jkim",    "Code Repository",   "Onboarding to the internal tools project",     "Approved", 58, 4,  "Approved for project work."),
    ("srivera", "CRM",               "Handling customer accounts for the West region", "Approved", 55, 20, None),
    ("tbrooks", "Finance Reporting", "Prepare monthly budget variance reports",      "Approved", 52, 30, "OK for month-end reporting."),
    ("cnguyen", "HR Database",       "Update employee records for new hires",        "Approved", 50, 6,  None),
    ("rpatel",  "Payroll",           "Cover payroll processing during team leave",   "Rejected", 48, 50, "Payroll access is limited to the payroll team. Ask them to run it for you."),
    ("pshah",   "Finance Reporting", "Review department spending",                   "Approved", 46, 26, "Approved for budget owners."),
    ("jkim",    "Payroll",           "Want to compare salary bands",                 "Rejected", 44, 10, "Not needed for your role."),
    ("mlee",    "HR Database",       "Run headcount reports for my team",            "Approved", 41, 72, None),
    ("cnguyen", "CRM",               "Support the sales team with data cleanup",     "Approved", 39, 3,  None),
    ("srivera", "Finance Reporting", "Quarter-end close support",                    "Rejected", 36, 48, "Close is finished. Please re-request next quarter."),
    ("tbrooks", "Code Repository",   "Fix bugs in reporting scripts",                "Approved", 33, 8,  None),
    ("rpatel",  "CRM",               "Customer follow-up calls",                     "Approved", 30, 14, None),
    ("jkim",    "HR Database",       "Look up colleague contact details",            "Rejected", 27, 5,  "Please use the company directory instead."),
    ("cnguyen", "Finance Reporting", "Pull revenue numbers for a presentation",      "Approved", 25, 96, "Approved for one quarter."),
    ("pshah",   "Payroll",           "Approve overtime for my team",                 "Rejected", 22, 40, "Overtime approvals go through the HR Database, not Payroll."),
    ("srivera", "Code Repository",   "Pair programming with the dev team",           "Approved", 19, 22, None),
    ("rpatel",  "Finance Reporting", "Monthly expense reconciliation",               "Approved", 16, 9,  None),
    ("tbrooks", "HR Database",       "Update the onboarding checklist",              "Approved", 12, 30, None),
    ("mlee",    "CRM",               "Review the key accounts pipeline",             "Approved", 9,  18, "Approved."),
    # Still waiting for a decision:
    ("jkim",    "Finance Reporting", "Analyze Q3 team spending",                     "Pending",  21, None, None),
    ("cnguyen", "Code Repository",   "Automate a weekly report",                     "Pending",  14, None, None),
    ("rpatel",  "HR Database",       "Update the emergency contact process",         "Pending",  8,  None, None),
    ("mlee",    "Code Repository",   "Review my team's code quality",                "Pending",  6,  None, None),
    ("srivera", "Payroll",           "Check my own tax withholding setup",           "Pending",  4,  None, None),
    ("tbrooks", "CRM",               "Help with customer escalations",               "Pending",  2,  None, None),
    ("pshah",   "HR Database",       "Prepare annual performance reviews",           "Pending",  1,  None, None),
]


def fmt(dt):
    """Format a datetime the way we store it: 'YYYY-MM-DD HH:MM:SS' in UTC."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def main():
    conn = db.connect()
    db.init_db(conn)  # drop and recreate all tables

    # --- Users ----------------------------------------------------------
    # Insert in list order so each manager already exists before their reports.
    user_ids = {}  # username -> id
    for username, name, role, manager_username in USERS:
        manager_id = user_ids.get(manager_username)  # None for the admin
        cur = conn.execute(
            "INSERT INTO users (name, username, password_hash, role, manager_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, username, generate_password_hash(DEMO_PASSWORD), role, manager_id),
        )
        user_ids[username] = cur.lastrowid
    manager_of = {u: m for u, _, _, m in USERS}

    # --- Systems --------------------------------------------------------
    system_ids = {}
    for name, description in SYSTEMS:
        cur = conn.execute(
            "INSERT INTO systems (name, description) VALUES (?, ?)", (name, description)
        )
        system_ids[name] = cur.lastrowid

    # --- Requests -------------------------------------------------------
    # Dates are relative to "now", so the dashboard always shows the last 60 days.
    now = datetime.now(timezone.utc).replace(microsecond=0)
    for i, (requester, system, reason, status, days_ago, hours, comment) in enumerate(REQUESTS):
        # Nudge the time of day a little per row so timestamps don't all look the same.
        created = now - timedelta(days=days_ago, hours=i % 7, minutes=(i * 13) % 60)
        if status == "Pending":
            decided_by, decided_at = None, None
        else:
            decided_by = user_ids[manager_of[requester]]
            decided_at = fmt(created + timedelta(hours=hours))
        conn.execute(
            "INSERT INTO access_requests "
            "(requester_id, system_id, reason, status, decided_by_id, "
            " decision_comment, created_at, decided_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_ids[requester], system_ids[system], reason, status,
             decided_by, comment, fmt(created), decided_at),
        )

    conn.commit()

    # --- Summary --------------------------------------------------------
    print(f"Created {db.DATABASE_PATH.name}")
    print(f"  {len(USERS)} users, {len(SYSTEMS)} systems, {len(REQUESTS)} requests")
    for status, count in conn.execute(
        "SELECT status, COUNT(*) FROM access_requests GROUP BY status ORDER BY status"
    ):
        print(f"    {status:<9} {count}")
    print(f"\nDemo logins (password for everyone: {DEMO_PASSWORD})")
    for username, name, role, _ in USERS:
        print(f"  {username:<9} {name:<14} {role}")
    conn.close()


if __name__ == "__main__":
    main()
