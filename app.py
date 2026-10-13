"""
The Flask application: configuration plus the page routes.

Start it with:   flask --app app run --debug
then open http://127.0.0.1:5000 in your browser.

A "route" maps a URL to a Python function. The function returns the page,
usually by filling in an HTML template from the templates/ folder.
"""
import os
import secrets
import sqlite3
from datetime import datetime, timezone

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   url_for)
from flask_wtf.csrf import CSRFError, CSRFProtect

import auth
from auth import login_required
from db import BASE_DIR, close_db, get_db

SECRET_KEY_FILE = BASE_DIR / ".secret_key"
MAX_REASON_LENGTH = 500


def now_utc():
    """Current time in the format we store in the database (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def load_secret_key():
    """
    Flask signs the session cookie with SECRET_KEY. Anyone who knows the key
    could forge a cookie and log in as anyone, so it must never be in the code
    or in git. We look for it in this order:
      1. the FLASK_SECRET_KEY environment variable, if it's set;
      2. otherwise the local .secret_key file (gitignored);
      3. if there's no file yet, we generate a random key and save it there.
    """
    key = os.environ.get("FLASK_SECRET_KEY")
    if key:
        return key
    if not SECRET_KEY_FILE.exists():
        SECRET_KEY_FILE.write_text(secrets.token_hex(32))
        SECRET_KEY_FILE.chmod(0o600)  # readable by your user account only
    return SECRET_KEY_FILE.read_text().strip()


app = Flask(__name__)
app.config["SECRET_KEY"] = load_secret_key()
# Browsers won't send the session cookie on cross-site form posts (extra CSRF defense).
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# CSRF protection: every POST must include a hidden csrf_token field (see
# templates). Requests without a valid token are rejected with a 400 error.
csrf = CSRFProtect(app)

# Close the DB connection at the end of every request.
app.teardown_appcontext(close_db)

# Plug in the login/logout routes from auth.py.
app.register_blueprint(auth.bp)


@app.template_filter("nice_time")
def nice_time(value):
    """
    Template filter: {{ some_timestamp | nice_time }}
    Turns '2026-10-13 14:05:00' into '13 Oct 2026, 14:05'. Empty values show a dash.
    """
    if not value:
        return "—"
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime("%d %b %Y, %H:%M")


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """The home URL just forwards to the right place."""
    if g.user is None:
        return redirect(url_for("auth.login"))
    return redirect(auth.home_url(g.user))


@app.route("/my-requests", methods=["GET", "POST"])
@login_required("employee", "manager")
def my_requests():
    """
    GET:  show the request form and this user's request history.
    POST: validate and save a new request, then redirect back here
          (Post/Redirect/Get, so refreshing the page doesn't resubmit).
    """
    db = get_db()
    systems = db.execute("SELECT id, name FROM systems ORDER BY name").fetchall()

    if request.method == "POST":
        system_id = request.form.get("system_id", type=int)  # None if missing or not a number
        reason = request.form.get("reason", "").strip()

        # Validate on the server. The HTML 'required' attribute is only a
        # convenience: anyone can send a POST without using our form.
        error = None
        if system_id not in {s["id"] for s in systems}:
            error = "Please choose a system."
        elif not reason:
            error = "Please enter a reason."
        elif len(reason) > MAX_REASON_LENGTH:
            error = f"Please keep the reason under {MAX_REASON_LENGTH} characters."
        elif db.execute(
            "SELECT 1 FROM access_requests "
            "WHERE requester_id = ? AND system_id = ? AND status = 'Pending'",
            (g.user["id"], system_id),
        ).fetchone():
            error = "You already have a pending request for that system."

        if error is None:
            try:
                db.execute(
                    "INSERT INTO access_requests (requester_id, system_id, reason, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (g.user["id"], system_id, reason, now_utc()),
                )
                db.commit()
            except sqlite3.IntegrityError:
                # The unique index in schema.sql caught a duplicate that slipped
                # past the check above (e.g. a double-click submitting twice at once).
                error = "You already have a pending request for that system."

        if error is None:
            flash("Request submitted. Your manager will review it.", "success")
            return redirect(url_for("my_requests"))

        # Show the form again with the error and what they typed.
        flash(error, "error")
        history = get_request_history(g.user["id"])
        return render_template("my_requests.html", systems=systems, history=history,
                               form=request.form), 400

    history = get_request_history(g.user["id"])
    return render_template("my_requests.html", systems=systems, history=history, form={})


def get_request_history(user_id):
    """All of one user's requests, newest first, with system and decider names."""
    return get_db().execute(
        """
        SELECT r.id, s.name AS system_name, r.reason, r.status,
               r.created_at, r.decided_at, r.decision_comment,
               d.name AS decided_by_name
        FROM access_requests r
        JOIN systems s     ON s.id = r.system_id
        LEFT JOIN users d  ON d.id = r.decided_by_id   -- LEFT: Pending has no decider
        WHERE r.requester_id = ?
        ORDER BY r.created_at DESC
        """,
        (user_id,),
    ).fetchall()


@app.route("/approvals")
@login_required("manager", "admin")
def approvals():
    """
    The approval queue: Pending requests from the people who report to me.
    For a manager that's their employees; for the admin it's the managers.
    """
    db = get_db()
    pending = db.execute(
        """
        SELECT r.id, u.name AS requester_name, s.name AS system_name,
               r.reason, r.created_at,
               CAST(julianday('now') - julianday(r.created_at) AS INTEGER) AS days_waiting
        FROM access_requests r
        JOIN users u   ON u.id = r.requester_id
        JOIN systems s ON s.id = r.system_id
        WHERE r.status = 'Pending'
          AND u.manager_id = ?          -- only my direct reports
          AND r.requester_id <> ?       -- never my own request
        ORDER BY r.created_at           -- oldest first: they've waited longest
        """,
        (g.user["id"], g.user["id"]),
    ).fetchall()

    # A short history of what I've decided, so I can see what just happened.
    recent = db.execute(
        """
        SELECT u.name AS requester_name, s.name AS system_name, r.status,
               r.decision_comment, r.decided_at
        FROM access_requests r
        JOIN users u   ON u.id = r.requester_id
        JOIN systems s ON s.id = r.system_id
        WHERE r.decided_by_id = ?
        ORDER BY r.decided_at DESC
        LIMIT 10
        """,
        (g.user["id"],),
    ).fetchall()

    return render_template("approvals.html", pending=pending, recent=recent)


@app.route("/approvals/<int:request_id>/decide", methods=["POST"])
@login_required("manager", "admin")
def decide(request_id):
    """
    Approve or reject one request. <int:request_id> in the URL becomes the
    request_id argument. Every rule is checked here on the server, because
    anyone can send this POST without using our page.
    """
    db = get_db()
    action = request.form.get("action")
    comment = request.form.get("comment", "").strip() or None  # empty -> NULL

    if action not in ("approve", "reject"):
        abort(400)
    if comment and len(comment) > MAX_REASON_LENGTH:
        flash(f"Please keep the comment under {MAX_REASON_LENGTH} characters.", "error")
        return redirect(url_for("approvals"))

    req = db.execute(
        """
        SELECT r.id, r.requester_id, r.status, u.manager_id, u.name AS requester_name,
               s.name AS system_name
        FROM access_requests r
        JOIN users u   ON u.id = r.requester_id
        JOIN systems s ON s.id = r.system_id
        WHERE r.id = ?
        """,
        (request_id,),
    ).fetchone()

    if req is None:
        abort(404)
    # Permission checks: it must be my direct report's request, and not my own.
    if req["manager_id"] != g.user["id"] or req["requester_id"] == g.user["id"]:
        abort(403)

    new_status = "Approved" if action == "approve" else "Rejected"
    # "AND status = 'Pending'" makes this safe if two clicks arrive at once:
    # only the first one changes a row, and rowcount tells us if we did.
    cur = db.execute(
        """
        UPDATE access_requests
        SET status = ?, decided_by_id = ?, decision_comment = ?, decided_at = ?
        WHERE id = ? AND status = 'Pending'
        """,
        (new_status, g.user["id"], comment, now_utc(), request_id),
    )
    db.commit()

    if cur.rowcount == 0:
        flash("That request was already decided.", "error")
    else:
        flash(f"{new_status} {req['requester_name']}'s request for {req['system_name']}.",
              "success")
    return redirect(url_for("approvals"))


# Placeholders for now. Each stage replaces one of these with the real page.


@app.route("/admin/audit-log")
@login_required("admin")
def audit_log():
    return render_template("placeholder.html", title="Audit Log", stage=5)


@app.route("/admin/dashboard")
@login_required("admin")
def dashboard():
    return render_template("placeholder.html", title="Dashboard", stage=5)


# ---------------------------------------------------------------------------
# Error pages
# ---------------------------------------------------------------------------

@app.errorhandler(403)
def forbidden(error):
    return render_template("error.html", code=403,
                           message="You don't have permission to do that."), 403


@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404,
                           message="That page doesn't exist."), 404


@app.errorhandler(CSRFError)
def csrf_error(error):
    return render_template("error.html", code=400,
                           message="Your form expired or was invalid. "
                                   "Go back, refresh the page, and try again."), 400
