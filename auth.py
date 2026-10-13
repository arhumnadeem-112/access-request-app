"""
Login, logout, and permission checks.

How logging in works:
  1. The user submits the login form with a username and password.
  2. We look up the user and compare the password against the stored hash.
  3. If it matches, we put their id in `session`. Flask stores the session in
     a cookie signed with SECRET_KEY, so the browser can't tamper with it.
  4. Before every request, load_logged_in_user() reads that id and loads the
     user row into `g.user`, which routes and templates can then use.

This file uses a Flask "Blueprint": a way to define routes in a separate file
and plug them into the app in app.py. Its route names get an "auth." prefix,
e.g. url_for("auth.login").
"""
from functools import wraps

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash

from db import get_db

bp = Blueprint("auth", __name__)

# Where each role lands after logging in (these are route names from app.py).
HOME_PAGE_FOR_ROLE = {
    "employee": "my_requests",
    "manager": "approvals",
    "admin": "dashboard",
}


def home_url(user):
    """The URL of the page this user should start on."""
    return url_for(HOME_PAGE_FOR_ROLE[user["role"]])


@bp.before_app_request
def load_logged_in_user():
    """Runs before EVERY request: set g.user to the logged-in user, or None."""
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = get_db().execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if g.user is None:
            # The user no longer exists (for example, the DB was reseeded).
            session.clear()


def login_required(*allowed_roles):
    """
    Decorator that protects a route.

        @app.route("/approvals")
        @login_required("manager", "admin")
        def approvals(): ...

    - Not logged in            -> redirect to the login page
    - Logged in, wrong role    -> 403 Forbidden
    - No roles listed          -> any logged-in user may enter
    This check happens on the server, so hiding a link is never the only protection.
    """
    def decorator(view):
        @wraps(view)  # keeps the original function's name, which Flask needs
        def wrapped_view(*args, **kwargs):
            if g.user is None:
                flash("Please log in first.", "error")
                return redirect(url_for("auth.login"))
            if allowed_roles and g.user["role"] not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped_view
    return decorator


@bp.route("/login", methods=["GET", "POST"])
def login():
    # Already logged in? Skip the form.
    if g.user is not None:
        return redirect(home_url(g.user))

    # GET = show the form. POST = the form was submitted.
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()

        # Same message whether the username or the password was wrong, so
        # the form doesn't reveal which usernames exist.
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid username or password.", "error")
            return render_template("login.html", username=username), 401

        # Start a fresh session (drops anything left from before), then remember the user.
        session.clear()
        session["user_id"] = user["id"]
        return redirect(home_url(user))

    return render_template("login.html")


# Logout is a POST (a button in a small form), not a plain link. That way a
# malicious page can't log you out with a hidden <img src="/logout">: POSTs
# need a valid CSRF token, links don't.
@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
