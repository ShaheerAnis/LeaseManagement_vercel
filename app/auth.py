import functools
from datetime import datetime, timezone, timedelta
from flask import g, session, redirect, url_for, flash, request
from app.models import User

def login_required(f):
    """
    Decorator to ensure a valid authenticated and approved user is logged in.
    Redirects unauthenticated users to the login page.
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.current_user:
            return redirect(url_for('main.login', next=request.url))
        if not g.current_user.is_approved:
            session.clear()
            flash('Your account is awaiting administrator approval before you can access LeaseFlow.', 'warning')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """
    Decorator to ensure only authenticated users with 'admin' role can access the view.
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not g.current_user:
            return redirect(url_for('main.login', next=request.url))
        if not g.current_user.is_approved:
            session.clear()
            flash('Your account is awaiting administrator approval.', 'warning')
            return redirect(url_for('main.login'))
        if not g.current_user.is_admin:
            flash('Administrator privileges are required to access this area.', 'danger')
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function
