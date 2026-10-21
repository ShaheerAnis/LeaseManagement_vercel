import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

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

    # Configure database and uploads
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'lease-manager-secret-key-dev-2026'),
        SQLALCHEMY_DATABASE_URI=database_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        UPLOAD_FOLDER=upload_dir,
        FALLBACK_UPLOAD_FOLDER=os.path.join(app.root_path, 'static', 'uploads'),
        MAX_CONTENT_LENGTH=32 * 1024 * 1024, # 32 MB max upload
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
            from datetime import datetime
            try:
                value = datetime.strptime(value, '%Y-%m-%d').date()
            except ValueError:
                return value
        return value.strftime(format)
    
    # Import and register blueprints / routes
    from app.routes import main_bp
    app.register_blueprint(main_bp)
    
    with app.app_context():
        db.create_all()
        
    return app
