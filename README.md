# System Access Request App

A small proof-of-concept web app for IT compliance.

- **Employees** request access to company systems.
- **Managers** approve or reject requests from their direct reports.
- **The admin (compliance)** reviews a full audit trail and a dashboard.

Built with **Python + Flask**, a **SQLite** database (a single file), HTML templates, plain CSS, and **Chart.js** for the dashboard charts. Everything runs on your own machine and works offline.

---

## 1. Setup (one time)

You need Python 3 from python.org; it was built and tested with Python 3.15. Check with `python3 --version`.

```bash
cd ~/Projects/access-request-app

# Create a virtual environment: a private folder of packages just for this project
python3 -m venv .venv

# Turn it on. Your prompt will start with (.venv)
source .venv/bin/activate

# Install Flask and Flask-WTF
pip install -r requirements.txt

# Create the database and load the demo data
python seed.py
```

## 2. Run it

```bash
cd ~/Projects/access-request-app
source .venv/bin/activate            # needed in each new terminal window
flask --app app run --debug
```

Open **http://127.0.0.1:5000** in your browser. Stop the server with **Ctrl+C**.

- `--debug` restarts the server automatically when you edit a file, and shows detailed error pages. Use it only on your own machine, never on a server other people can reach.
- To reset all data back to the demo state at any time, run `python seed.py`. It deletes everything in `access.db` and reloads the demo data.

## 3. Demo logins

The password for every demo user is **`demo123`**.

| Username  | Name          | Role     | Reports to | Lands on       |
|-----------|---------------|----------|------------|----------------|
| `admin`   | Alex Morgan   | admin    | —          | Dashboard      |
| `pshah`   | Priya Shah    | manager  | admin      | Approval Queue |
| `mlee`    | Marcus Lee    | manager  | admin      | Approval Queue |
| `jkim`    | Jordan Kim    | employee | pshah      | My Requests    |
| `srivera` | Sam Rivera    | employee | pshah      | My Requests    |
| `tbrooks` | Taylor Brooks | employee | pshah      | My Requests    |
| `cnguyen` | Casey Nguyen  | employee | mlee       | My Requests    |
| `rpatel`  | Riley Patel   | employee | mlee       | My Requests    |

The demo data also includes 5 systems and 26 requests (14 Approved, 5 Rejected, 7 Pending), spread over the last 60 days. All names are made up.

## 4. What each role can do

| Role | Pages | Notes |
|---|---|---|
| Employee | **My Requests** | Request access to a system (with a reason), and see the status of their own requests. |
| Manager | **Approval Queue**, **My Requests** | Approve or reject pending requests from their direct reports, with an optional comment. Their own requests go to the admin. |
| Admin | **Dashboard**, **Audit Log**, **Approvals** | Read-only view of everything. The one exception is the Approvals page, where the admin decides the managers' requests. |

**Approval routing rule:** a request always goes to the requester's manager (`users.manager_id`). Managers report to the admin, so the admin approves managers' requests without any special-case code.

## 5. How the app is structured

```
access-request-app/
├── app.py              Creates the Flask app (secret key, CSRF) and all page routes
├── auth.py             Login, logout, and the @login_required(...) permission check
├── db.py               Opens/closes the SQLite connection
├── schema.sql          The 3 tables (users, systems, access_requests) in plain SQL
├── seed.py             Wipes the DB and loads the demo data
├── requirements.txt    Python packages to install
├── templates/          HTML pages (Jinja templates)
│   ├── base.html           Shared layout: top nav bar, flash messages
│   ├── login.html
│   ├── my_requests.html    Employee/manager: request form + history
│   ├── approvals.html      Manager/admin: approval queue
│   ├── audit_log.html      Admin: every request, with filters
│   ├── dashboard.html      Admin: stat tiles + charts
│   └── error.html          403 / 404 / 400 pages
├── static/
│   ├── style.css           All styling (colors are variables at the top)
│   └── vendor/chart.umd.js Chart.js 4.4.7, stored locally so it works offline
├── access.db           The database (created by seed.py, not in git)
└── .secret_key         Auto-generated signing key (not in git)
```

### Pages (routes in `app.py` and `auth.py`)

| URL | Who | What |
|---|---|---|
| `/login` | anyone | Login form |
| `/logout` (POST) | logged in | Log out |
| `/my-requests` | employee, manager | Request form + own history |
| `/approvals` | manager, admin | Pending requests from direct reports + recent decisions |
| `/approvals/<id>/decide` (POST) | manager, admin | Approve or reject one request |
| `/admin/audit-log` | admin | Every request; filter by `?system_id=` and `?status=` |
| `/admin/dashboard` | admin | Pending count, approved vs rejected, requests by system, average time to decision, oldest open request |

### How a request flows through the code

1. **The browser sends a request**, e.g. a POST to `/my-requests` with the form fields.
2. **Before every request**, `auth.load_logged_in_user()` reads the user id from the signed session cookie and loads that user into `g.user`.
3. **The decorator** `@login_required("employee", "manager")` checks the role. It redirects to the login page if you're not logged in, and returns **403** if your role isn't allowed.
4. **The route function** validates the input, runs SQL through `get_db()`, and either:
   - renders a template, or
   - redirects. After a successful form POST the app always redirects (the "Post/Redirect/Get" pattern), so refreshing the page doesn't submit the form twice.
5. **The template** extends `base.html` and fills in its `content` block. Jinja automatically escapes text, so a reason like `<script>` is shown as text and never runs.

### Database

Three tables, defined in `schema.sql`:

- `users`: `id`, `name`, `username`, `password_hash`, `role`, `manager_id` (points to another user)
- `systems`: `id`, `name`, `description`
- `access_requests`: `id`, `requester_id`, `system_id`, `reason`, `status`, `decided_by_id`, `decision_comment`, `created_at`, `decided_at`

Timestamps are stored as UTC text (`YYYY-MM-DD HH:MM:SS`). The dashboard calculates the average time to decision in SQL with `julianday(decided_at) - julianday(created_at)`.

To explore the data directly:

```bash
sqlite3 -header -column access.db "SELECT status, COUNT(*) FROM access_requests GROUP BY status;"
```

## 6. Security basics

- **Passwords are hashed.** They're stored with Werkzeug's `generate_password_hash` and checked with `check_password_hash`, never in plain text. A failed login gives the same message whether the username or the password was wrong.
- **Every page and action checks permissions on the server.** Hiding a button is only for convenience. For example, approving a request checks three things:
  - the request is still Pending;
  - the requester's manager is the current user;
  - the requester is not the current user.
- **Nobody can approve their own request.** This is checked in Python and enforced again by a `CHECK` constraint in the database.
- **No duplicate pending requests.** A Python check shows a friendly message. A partial unique index (`... WHERE status = 'Pending'`) in the database also blocks duplicates, even if two submits arrive at the same moment.
- **SQL injection is prevented.** Every value is passed to SQLite as a `?` parameter, never pasted into the SQL text.

### The secret key

Flask signs the login session cookie with a secret key. Anyone who knows the key could forge a cookie and log in as anyone, so **it is never written in the code or committed to git**. `app.py` (`load_secret_key()`) finds it in this order:

1. The **`FLASK_SECRET_KEY` environment variable**, if it's set:
   ```bash
   export FLASK_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
   ```
2. Otherwise, the **`.secret_key` file** in the project folder.
3. If that file doesn't exist yet, the app **creates it on first run** with a random key, readable only by your user account.

`.secret_key` is listed in `.gitignore`. If you delete it, a new key is generated and everyone is simply logged out.

### CSRF protection

CSRF (cross-site request forgery) is when another website tricks your browser into submitting a form to this app while you're logged in. Flask-WTF's `CSRFProtect` blocks it:

- Every form includes a hidden field, `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">`.
- Any POST without a valid token is rejected with a **400** error page.
- **Log out** is a small POST form too (not a plain link), so another site can't log you out.
- Read-only GET pages, like the audit log filters, don't need a token.

### What a production app would add

This is a learning proof-of-concept. A real deployment would also need:
- HTTPS, and a production web server instead of `flask run`
- single sign-on
- password reset
- rate limiting on the login page
- email notifications
- a server database such as PostgreSQL
- automated tests and backups

These were out of scope on purpose.

## 7. Rolling back with git

Each build stage is a separate commit:

```bash
git log --oneline              # list commits, newest first
git diff HEAD~1                # what changed in the most recent commit
git checkout <hash>            # look at an older version (read-only "detached" state)
git checkout main              # come back to the latest version
git reset --hard <hash>        # PERMANENTLY go back to <hash>, discarding later commits and uncommitted changes
```

After moving to a different version, run `python seed.py` in case the database layout changed.

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| `command not found: flask` | Turn on the virtual environment first: `source .venv/bin/activate` |
| `no such table: users` | Create the database: `python seed.py` |
| Port 5000 is busy (on macOS the AirPlay Receiver can use it) | Use another port: `flask --app app run --debug --port 5001` |
| "Your form expired or was invalid" | The page was open for a long time or the secret key changed. Refresh the page and try again. |
| You're suddenly logged out | `.secret_key` (or `FLASK_SECRET_KEY`) changed, so old session cookies are no longer valid. Log in again. |
