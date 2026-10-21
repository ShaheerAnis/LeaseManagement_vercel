import os
from datetime import datetime, timezone, timedelta
from flask import Flask, session, g
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

db = SQLAlchemy()

def ensure_admin_and_migrate(app):
    """
    Ensures that database schema migrations (user_id columns) are applied,
    provisions the primary admin account for Shaheer Anis, and associates
    all existing unassigned leases and counterparties to him.
    """
    with app.app_context():
        db.create_all()
        try:
            inspector = inspect(db.engine)
            existing_tables = inspector.get_table_names()
            
            # Check and add user_id column to leases if missing
            if 'leases' in existing_tables:
                lease_columns = [col['name'] for col in inspector.get_columns('leases')]
                if 'user_id' not in lease_columns:
                    with db.engine.connect() as conn:
                        conn.execute(text("ALTER TABLE leases ADD COLUMN user_id INTEGER REFERENCES users(id)"))
                        conn.commit()

            # Check and add user_id column to counterparties if missing
            if 'counterparties' in existing_tables:
                cp_columns = [col['name'] for col in inspector.get_columns('counterparties')]
                if 'user_id' not in cp_columns:
                    with db.engine.connect() as conn:
                        conn.execute(text("ALTER TABLE counterparties ADD COLUMN user_id INTEGER REFERENCES users(id)"))
                        conn.commit()

            # Ensure the primary Admin user (Shaheer Anis) exists and is active
            from app.models import User, Lease, Counterparty
            admin_user = User.query.filter_by(username='shaheer.anis').first()
            if not admin_user:
                admin_user = User(
                    username='shaheer.anis',
                    full_name='Shaheer Anis',
                    email='shaheer.anis@leaseflow.io',
                    role='admin',
                    status='approved',
                    approved_at=datetime.now(timezone.utc)
                )
                admin_user.set_password('shaheer.1anis')
                db.session.add(admin_user)
                db.session.commit()
            else:
                # Keep admin credentials and role guaranteed
                admin_user.role = 'admin'
                admin_user.status = 'approved'
                if not admin_user.check_password('shaheer.1anis'):
                    admin_user.set_password('shaheer.1anis')
                db.session.commit()

            # Assign all existing data to Shaheer Anis
            Lease.query.filter(Lease.user_id.is_(None)).update({Lease.user_id: admin_user.id})
            Counterparty.query.filter(Counterparty.user_id.is_(None)).update({Counterparty.user_id: admin_user.id})
            db.session.commit()

        except Exception as e:
            # Fallback for testing environments or errors
            db.session.rollback()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    
    is_vercel = bool(os.environ.get('VERCEL'))
    
    # In serverless environments like Vercel, the filesystem is read-only except /tmp
    if is_vercel:
        instance_dir = '/tmp/instance'
        upload_dir = '/tmp/uploads'
    else:
        instance_dir = app.instance_path
        upload_dir = os.path.join(app.root_path, 'static', 'uploads')
        
    try:
        os.makedirs(instance_dir, exist_ok=True)
    except OSError:
        instance_dir = '/tmp/instance'
        os.makedirs(instance_dir, exist_ok=True)

    try:
        os.makedirs(upload_dir, exist_ok=True)
    except OSError:
        upload_dir = '/tmp/uploads'
        os.makedirs(upload_dir, exist_ok=True)

    db_path = os.path.join(instance_dir, 'lease_management.db')

    # If running on Vercel with SQLite and bundled seed database exists, copy it over to /tmp
    bundled_db = os.path.join(app.root_path, '..', 'instance', 'lease_management.db')
    if is_vercel and os.path.exists(bundled_db) and not os.path.exists(db_path):
        import shutil
        try:
            shutil.copy2(bundled_db, db_path)
        except Exception:
            pass

    # Support external database (e.g. Neon / Supabase Postgres) via DATABASE_URL
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
    else:
        database_url = f"sqlite:///{db_path}"

    # Configure database, uploads, and secure sessions
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'lease-manager-secret-key-prod-secure-2026-shaheer'),
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=upload_dir,
        FALLBACK_UPLOAD_FOLDER=os.path.join(app.root_path, 'static', 'uploads'),
        MAX_CONTENT_LENGTH=32 * 1024 * 1024, # 32 MB max upload
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    )
    
    if test_config:
        app.config.update(test_config)
        
    db.init_app(app)
    
    # Register Jinja custom filters
    @app.template_filter('currency')
    def currency_filter(value):
        if value is None:
            return "0.00"
        try:
            return f"{float(value):,.2f}"
        except (ValueError, TypeError):
            return str(value)
            
    @app.template_filter('date_format')
    def date_format_filter(value, format='%b %d, %Y'):
        if value is None:
            return ""
        if isinstance(value, str):
            try:
                value = datetime.strptime(value, '%Y-%m-%d').date()
            except ValueError:
                return value
        return value.strftime(format)
    
    # Request lifecycle: authenticate user from session
    @app.before_request
    def load_logged_in_user():
        user_id = session.get('user_id')
        if user_id is None:
            g.current_user = None
        else:
            from app.models import User
            user = db.session.get(User, user_id)
            if user and user.is_approved:
                g.current_user = user
            else:
                session.clear()
                g.current_user = None

    # Context processor: inject current_user and pending approval counter
    @app.context_processor
    def inject_auth_context():
        from app.models import User
        pending_count = 0
        current_u = g.get('current_user')
        if current_u and current_u.is_admin:
            try:
                pending_count = User.query.filter_by(status='pending').count()
            except Exception:
                pending_count = 0
        return {
            'current_user': current_u,
            'pending_approvals_count': pending_count
        }

    # Import and register blueprints / routes
    from app.routes import main_bp
    app.register_blueprint(main_bp)
    
    ensure_admin_and_migrate(app)
        
    return app
