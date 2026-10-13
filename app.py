"""
The Flask application: configuration plus the page routes.

Start it with:   flask --app app run --debug
then open http://127.0.0.1:5000 in your browser.

A "route" maps a URL to a Python function. The function returns the page,
usually by filling in an HTML template from the templates/ folder.
"""
import os
import secrets

from flask import Flask, g, redirect, render_template, url_for
from flask_wtf.csrf import CSRFError, CSRFProtect

import auth
from auth import login_required
from db import BASE_DIR, close_db

SECRET_KEY_FILE = BASE_DIR / ".secret_key"


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


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """The home URL just forwards to the right place."""
    if g.user is None:
        return redirect(url_for("auth.login"))
    return redirect(auth.home_url(g.user))


# Placeholders for now. Each stage replaces one of these with the real page.
@app.route("/my-requests")
@login_required("employee", "manager")
def my_requests():
    return render_template("placeholder.html", title="My Requests", stage=3)


@app.route("/approvals")
@login_required("manager", "admin")
def approvals():
    return render_template("placeholder.html", title="Approval Queue", stage=4)


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
