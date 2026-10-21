import os
import re
import uuid
from datetime import datetime, date, timezone, timedelta
from urllib.parse import urlparse
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory, jsonify, abort, session, g
from werkzeug.utils import secure_filename
from app import db
from app.models import Lease, Payment, Document, Counterparty, User
from app.auth import login_required, admin_required
from app.calculations import calculate_lease_metrics

main_bp = Blueprint('main', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'pdf', 'doc', 'docx'}

def is_safe_redirect_url(target):
    """Ensure redirect URL is local to prevent open redirect vulnerabilities."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(target)
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc or not test_url.netloc

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_type(filename):
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    if ext in {'png', 'jpg', 'jpeg', 'webp'}:
        return 'image'
    elif ext == 'pdf':
        return 'pdf'
    return 'document'

def save_uploaded_file(file, description="", lease_id=None, payment_id=None):
    if not file or file.filename == '':
        return None
    if allowed_file(file.filename):
        original_name = secure_filename(file.filename)
        unique_name = f"{uuid.uuid4().hex}_{original_name}"
        upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
        file.save(upload_path)
        file_size = os.path.getsize(upload_path)
        
        doc = Document(
            lease_id=lease_id,
            payment_id=payment_id,
            filename=unique_name,
            original_filename=original_name,
            file_type=get_file_type(original_name),
            file_size=file_size,
            description=description or original_name
        )
        db.session.add(doc)
        return doc
    return None

def save_multiple_files(file_list, base_description="", lease_id=None, payment_id=None):
    saved_docs = []
    for file in file_list:
        if file and file.filename != '':
            desc = base_description if base_description else file.filename
            doc = save_uploaded_file(file, description=desc, lease_id=lease_id, payment_id=payment_id)
            if doc:
                saved_docs.append(doc)
    return saved_docs

def get_or_create_counterparty(name, contact_info="", user_id=None):
    if not name or not name.strip():
        return None
    cleaned_name = name.strip()
    query = Counterparty.query.filter(Counterparty.name.ilike(cleaned_name))
    if user_id:
        query = query.filter_by(user_id=user_id)
    cp = query.first()
    if not cp:
        cp = Counterparty(
            user_id=user_id,
            name=cleaned_name,
            phone=contact_info.strip() if contact_info else None
        )
        db.session.add(cp)
        db.session.flush()
    else:
        if contact_info and not cp.phone:
            cp.phone = contact_info.strip()
            db.session.flush()
    return cp


# =========================================================
# AUTHENTICATION ROUTES (LOGIN, SIGNUP, LOGOUT)
# =========================================================

@main_bp.route('/login', methods=['GET', 'POST'])
def login():
    if g.get('current_user'):
        return redirect(url_for('main.dashboard'))

    next_url = request.args.get('next', '')

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        if not username or not password:
            flash('Please enter both username and password.', 'danger')
            return render_template('auth/login.html', next=next_url)

        user = User.query.filter(User.username.ilike(username)).first()

        # Brute-force lockout check
        if user and user.locked_until:
            now = datetime.now(timezone.utc)
            # Make sure locked_until is timezone-aware
            locked_dt = user.locked_until if user.locked_until.tzinfo else user.locked_until.replace(tzinfo=timezone.utc)
            if locked_dt > now:
                mins_left = max(1, int((locked_dt - now).total_seconds() // 60))
                flash(f'Account temporarily locked due to too many failed attempts. Try again in {mins_left} minute(s).', 'danger')
                return render_template('auth/login.html', next=next_url)

        # Validate password
        if not user or not user.check_password(password):
            if user:
                user.failed_logins = (user.failed_logins or 0) + 1
                if user.failed_logins >= 5:
                    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
                db.session.commit()
            flash('Invalid username or password. Please verify your credentials.', 'danger')
            return render_template('auth/login.html', next=next_url)

        # Reset failed login count on valid credentials
        user.failed_logins = 0
        user.locked_until = None

        # Check approval status
        if user.status == 'pending':
            db.session.commit()
            flash('Your account is awaiting approval by the administrator (Shaheer Anis). You cannot log in until approved.', 'warning')
            return render_template('auth/login.html', next=next_url)

        if user.status == 'rejected':
            db.session.commit()
            flash('Your account access request has been declined. Please contact the administrator.', 'danger')
            return render_template('auth/login.html', next=next_url)

        # User is approved -> Establish secure session
        session.clear() # Prevent session fixation
        session['user_id'] = user.id
        session.permanent = remember
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()

        flash(f'Welcome back, {user.full_name or user.username}!', 'success')

        if next_url and is_safe_redirect_url(next_url):
            return redirect(next_url)
        return redirect(url_for('main.dashboard'))

    return render_template('auth/login.html', next=next_url)


@main_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if g.get('current_user'):
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validations
        if not username or not password or not confirm_password:
            flash('Username, password, and confirmation are required.', 'danger')
            return render_template('auth/signup.html', username=username, full_name=full_name, email=email)

        if not re.match(r'^[a-z0-9._]{3,30}$', username):
            flash('Username must be 3-30 characters long and contain only letters, numbers, dots, or underscores.', 'danger')
            return render_template('auth/signup.html', username=username, full_name=full_name, email=email)

        if len(password) < 8:
            flash('Password must be at least 8 characters long for security.', 'danger')
            return render_template('auth/signup.html', username=username, full_name=full_name, email=email)

        if password != confirm_password:
            flash('Passwords do not match. Please re-enter them.', 'danger')
            return render_template('auth/signup.html', username=username, full_name=full_name, email=email)

        existing_user = User.query.filter(User.username.ilike(username)).first()
        if existing_user:
            flash(f'Username "{username}" is already taken. Please choose another.', 'danger')
            return render_template('auth/signup.html', username=username, full_name=full_name, email=email)

        # Create user with 'pending' status
        new_user = User(
            username=username,
            full_name=full_name or username,
            email=email or None,
            role='user',
            status='pending',
            created_at=datetime.now(timezone.utc)
        )
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        flash(
            f'Registration submitted! Your account ({username}) is currently PENDING approval by the administrator (Shaheer). '
            'You will be able to log in once your account has been reviewed and accepted.',
            'info'
        )
        return redirect(url_for('main.login'))

    return render_template('auth/signup.html')


@main_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    flash('You have been securely logged out.', 'info')
    return redirect(url_for('main.login'))


# =========================================================
# ADMIN USER MANAGEMENT & APPROVAL ROUTES
# =========================================================

@main_bp.route('/admin/users')
@admin_required
def admin_users():
    tab = request.args.get('tab', 'all')
    search = request.args.get('search', '').strip()

    query = User.query

    if tab == 'pending':
        query = query.filter_by(status='pending')
    elif tab == 'approved':
        query = query.filter_by(status='approved')
    elif tab == 'rejected':
        query = query.filter_by(status='rejected')

    if search:
        query = query.filter(
            (User.username.ilike(f'%{search}%')) |
            (User.full_name.ilike(f'%{search}%')) |
            (User.email.ilike(f'%{search}%'))
        )

    users = query.order_by(
        db.case((User.status == 'pending', 0), else_=1),
        User.created_at.desc()
    ).all()

    total_count = User.query.count()
    pending_count = User.query.filter_by(status='pending').count()
    approved_count = User.query.filter_by(status='approved').count()
    admin_count = User.query.filter_by(role='admin').count()

    return render_template(
        'admin/users.html',
        users=users,
        current_tab=tab,
        search=search,
        total_count=total_count,
        pending_count=pending_count,
        approved_count=approved_count,
        admin_count=admin_count
    )


@main_bp.route('/admin/users/<int:user_id>/approve', methods=['POST'])
@admin_required
def admin_approve_user(user_id):
    user = db.get_or_404(User, user_id)
    user.status = 'approved'
    user.approved_at = datetime.now(timezone.utc)
    db.session.commit()
    flash(f'User "{user.username}" has been APPROVED. They can now log in and manage their leases.', 'success')
    return redirect(url_for('main.admin_users'))


@main_bp.route('/admin/users/<int:user_id>/reject', methods=['POST'])
@admin_required
def admin_reject_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == g.current_user.id:
        flash('You cannot reject your own account.', 'danger')
        return redirect(url_for('main.admin_users'))

    user.status = 'rejected'
    db.session.commit()
    flash(f'User "{user.username}" has been REJECTED.', 'info')
    return redirect(url_for('main.admin_users'))


@main_bp.route('/admin/users/<int:user_id>/toggle-role', methods=['POST'])
@admin_required
def admin_toggle_role(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == g.current_user.id:
        flash('You cannot change your own admin role.', 'danger')
        return redirect(url_for('main.admin_users'))

    user.role = 'user' if user.role == 'admin' else 'admin'
    db.session.commit()
    flash(f'User "{user.username}" role updated to {user.role.upper()}.', 'success')
    return redirect(url_for('main.admin_users'))


@main_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == g.current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('main.admin_users'))

    username = user.username
    db.session.delete(user)
    db.session.commit()
    flash(f'User "{username}" and all their associated records have been permanently deleted.', 'info')
    return redirect(url_for('main.admin_users'))


# =========================================================
# APPLICATION CORE ROUTES (SCOPED TO CURRENT USER)
# =========================================================

@main_bp.route('/')
@login_required
def dashboard():
    all_leases = Lease.query.filter_by(user_id=g.current_user.id).order_by(Lease.created_at.desc()).all()
    
    total_payable_balance = 0.0
    total_receivable_balance = 0.0
    total_payable_monthly = 0.0
    total_receivable_monthly = 0.0
    active_payable_count = 0
    active_receivable_count = 0
    
    leases_with_metrics = []
    for lease in all_leases:
        metrics = calculate_lease_metrics(lease)
        leases_with_metrics.append({
            'lease': lease,
            'metrics': metrics
        })
        
        if lease.status == 'active':
            if lease.lease_type == 'payable':
                total_payable_balance += metrics['remaining_balance']
                total_payable_monthly += metrics['remaining_monthly_amount']
                active_payable_count += 1
            else:
                total_receivable_balance += metrics['remaining_balance']
                total_receivable_monthly += metrics['remaining_monthly_amount']
                active_receivable_count += 1

    recent_payments = (
        Payment.query.join(Lease)
        .filter(Lease.user_id == g.current_user.id)
        .order_by(Payment.payment_date.desc(), Payment.id.desc())
        .limit(6)
        .all()
    )
    
    return render_template(
        'dashboard.html',
        leases_with_metrics=leases_with_metrics[:6],
        total_leases=len(all_leases),
        active_payable_count=active_payable_count,
        active_receivable_count=active_receivable_count,
        total_payable_balance=total_payable_balance,
        total_receivable_balance=total_receivable_balance,
        total_payable_monthly=total_payable_monthly,
        total_receivable_monthly=total_receivable_monthly,
        recent_payments=recent_payments
    )


@main_bp.route('/leases')
@login_required
def lease_list():
    lease_type = request.args.get('type', 'all')
    status = request.args.get('status', 'all')
    category = request.args.get('category', 'all')
    search = request.args.get('search', '').strip()
    
    query = Lease.query.filter_by(user_id=g.current_user.id)
    
    if lease_type in ['payable', 'receivable']:
        query = query.filter_by(lease_type=lease_type)
    if status in ['active', 'completed', 'cancelled']:
        query = query.filter_by(status=status)
    if category != 'all' and category:
        query = query.filter_by(category=category)
    if search:
        query = query.filter(
            (Lease.title.ilike(f'%{search}%')) | (Lease.party_name.ilike(f'%{search}%'))
        )
        
    leases = query.order_by(Lease.created_at.desc()).all()
    leases_with_metrics = [{'lease': l, 'metrics': calculate_lease_metrics(l)} for l in leases]
    
    # Get distinct categories for current user
    categories = [r[0] for r in db.session.query(Lease.category).filter_by(user_id=g.current_user.id).distinct().all() if r[0]]
    
    return render_template(
        'leases/list.html',
        leases_with_metrics=leases_with_metrics,
        current_type=lease_type,
        current_status=status,
        current_category=category,
        search=search,
        categories=categories
    )


@main_bp.route('/leases/new', methods=['GET', 'POST'])
@login_required
def lease_create():
    counterparties = Counterparty.query.filter_by(user_id=g.current_user.id).order_by(Counterparty.name.asc()).all()
    selected_party_id = request.args.get('party_id')
    preselected_party = Counterparty.query.filter_by(id=int(selected_party_id), user_id=g.current_user.id).first() if selected_party_id and selected_party_id.isdigit() else None
    
    if request.method == 'POST':
        try:
            title = request.form.get('title', '').strip()
            lease_type = request.form.get('lease_type', 'payable')
            party_name = request.form.get('party_name', '').strip()
            party_contact = request.form.get('party_contact', '').strip()
            total_amount = float(request.form.get('total_amount', 0))
            tenure_months = int(request.form.get('tenure_months', 1))
            start_date_str = request.form.get('start_date')
            category = request.form.get('category', 'Electronics').strip()
            notes = request.form.get('notes', '').strip()
            
            if not title or not party_name or total_amount <= 0 or tenure_months <= 0:
                flash('Please provide valid title, party name, total amount, and duration.', 'danger')
                return redirect(url_for('main.lease_create'))
                
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else date.today()
            
            # Find or auto-create Counterparty scoped to current user
            cp = get_or_create_counterparty(party_name, party_contact, user_id=g.current_user.id)
            
            lease = Lease(
                user_id=g.current_user.id,
                title=title,
                lease_type=lease_type,
                counterparty_id=cp.id if cp else None,
                party_name=cp.name if cp else party_name,
                party_contact=party_contact or (cp.phone if cp else None),
                total_amount=total_amount,
                tenure_months=tenure_months,
                start_date=start_date,
                category=category,
                notes=notes,
                status='active'
            )
            db.session.add(lease)
            db.session.flush() # get lease.id
            
            # Check for contract documents
            contract_files = request.files.getlist('contract_doc') or request.files.getlist('contract_docs')
            if contract_files:
                save_multiple_files(
                    contract_files,
                    base_description=f"Agreement / Document for {title}",
                    lease_id=lease.id
                )
            
            # Check for initial down payment
            down_payment_amt = float(request.form.get('initial_payment_amount', 0) or 0)
            if down_payment_amt > 0:
                p_date_str = request.form.get('initial_payment_date')
                p_date = datetime.strptime(p_date_str, '%Y-%m-%d').date() if p_date_str else start_date
                p_method = request.form.get('initial_payment_method', 'Bank Transfer')
                p_ref = request.form.get('initial_payment_ref', '').strip()
                p_type = request.form.get('initial_payment_type', 'down_payment')
                
                payment = Payment(
                    lease_id=lease.id,
                    amount=down_payment_amt,
                    payment_date=p_date,
                    payment_type=p_type,
                    payment_method=p_method,
                    reference_no=p_ref,
                    notes='Initial down payment / 1st installment on creation'
                )
                db.session.add(payment)
                db.session.flush()
                
                receipt_files = request.files.getlist('initial_payment_receipt') or request.files.getlist('initial_payment_receipts')
                if receipt_files:
                    save_multiple_files(
                        receipt_files,
                        base_description=f"Receipt for payment of {down_payment_amt:,.2f}",
                        lease_id=lease.id,
                        payment_id=payment.id
                    )
            
            if lease.total_paid >= lease.total_amount:
                lease.status = 'completed'
                
            db.session.commit()
            flash(f'Lease "{title}" successfully created for {lease.party_name}!', 'success')
            return redirect(url_for('main.lease_detail', id=lease.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating lease: {str(e)}', 'danger')
            return redirect(url_for('main.lease_create'))
            
    return render_template('leases/form.html', lease=None, today=date.today(), counterparties=counterparties, preselected_party=preselected_party)


@main_bp.route('/leases/<int:id>')
@login_required
def lease_detail(id):
    lease = Lease.query.filter_by(id=id, user_id=g.current_user.id).first_or_404()
    metrics = calculate_lease_metrics(lease)
    return render_template('leases/detail.html', lease=lease, metrics=metrics, today=date.today())


@main_bp.route('/leases/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def lease_edit(id):
    lease = Lease.query.filter_by(id=id, user_id=g.current_user.id).first_or_404()
    counterparties = Counterparty.query.filter_by(user_id=g.current_user.id).order_by(Counterparty.name.asc()).all()
    
    if request.method == 'POST':
        try:
            lease.title = request.form.get('title', '').strip()
            lease.lease_type = request.form.get('lease_type', 'payable')
            party_name = request.form.get('party_name', '').strip()
            party_contact = request.form.get('party_contact', '').strip()
            
            cp = get_or_create_counterparty(party_name, party_contact, user_id=g.current_user.id)
            lease.counterparty_id = cp.id if cp else None
            lease.party_name = cp.name if cp else party_name
            lease.party_contact = party_contact or (cp.phone if cp else None)
            
            lease.total_amount = float(request.form.get('total_amount', lease.total_amount))
            lease.tenure_months = int(request.form.get('tenure_months', lease.tenure_months))
            
            start_date_str = request.form.get('start_date')
            if start_date_str:
                lease.start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
                
            lease.category = request.form.get('category', lease.category).strip()
            lease.status = request.form.get('status', lease.status)
            lease.notes = request.form.get('notes', '').strip()
            
            db.session.commit()
            flash('Lease details successfully updated.', 'success')
            return redirect(url_for('main.lease_detail', id=lease.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating lease: {str(e)}', 'danger')
            
    return render_template('leases/form.html', lease=lease, today=date.today(), counterparties=counterparties)


@main_bp.route('/leases/<int:id>/delete', methods=['POST'])
@login_required
def lease_delete(id):
    lease = Lease.query.filter_by(id=id, user_id=g.current_user.id).first_or_404()
    title = lease.title
    
    # Delete uploaded files from disk
    for doc in lease.documents:
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], doc.filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass
                
    db.session.delete(lease)
    db.session.commit()
    flash(f'Lease "{title}" and all its records have been deleted.', 'info')
    return redirect(url_for('main.lease_list'))


@main_bp.route('/leases/<int:id>/payments', methods=['POST'])
@login_required
def payment_create(id):
    lease = Lease.query.filter_by(id=id, user_id=g.current_user.id).first_or_404()
    try:
        amount = float(request.form.get('amount', 0))
        if amount <= 0:
            flash('Please provide a valid payment amount greater than zero.', 'danger')
            return redirect(url_for('main.lease_detail', id=lease.id))
            
        p_date_str = request.form.get('payment_date')
        p_date = datetime.strptime(p_date_str, '%Y-%m-%d').date() if p_date_str else date.today()
        p_type = request.form.get('payment_type', 'installment')
        p_method = request.form.get('payment_method', 'Bank Transfer')
        p_ref = request.form.get('reference_no', '').strip()
        notes = request.form.get('notes', '').strip()
        
        payment = Payment(
            lease_id=lease.id,
            amount=amount,
            payment_date=p_date,
            payment_type=p_type,
            payment_method=p_method,
            reference_no=p_ref,
            notes=notes
        )
        db.session.add(payment)
        db.session.flush()
        
        receipt_files = request.files.getlist('receipt') or request.files.getlist('receipts')
        if receipt_files:
            save_multiple_files(
                receipt_files,
                base_description=f"Receipt for payment of {amount:,.2f} on {p_date}",
                lease_id=lease.id,
                payment_id=payment.id
            )
                
        db.session.commit()
        
        if lease.remaining_balance <= 0.001 and lease.status == 'active':
            lease.status = 'completed'
            db.session.commit()
            flash(f'Payment of {amount:,.2f} recorded! Lease is now fully settled and completed.', 'success')
        else:
            flash(f'Payment of {amount:,.2f} successfully recorded.', 'success')
            
    except Exception as e:
        db.session.rollback()
        flash(f'Error recording payment: {str(e)}', 'danger')
        
    return redirect(url_for('main.lease_detail', id=lease.id))


@main_bp.route('/payments/<int:id>/delete', methods=['POST'])
@login_required
def payment_delete(id):
    payment = (
        Payment.query.join(Lease)
        .filter(Payment.id == id, Lease.user_id == g.current_user.id)
        .first_or_404()
    )
    lease_id = payment.lease_id
    
    for doc in payment.documents:
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], doc.filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass
                
    db.session.delete(payment)
    db.session.commit()
    
    lease = db.session.get(Lease, lease_id)
    if lease and lease.status == 'completed' and lease.remaining_balance > 0.001:
        lease.status = 'active'
        db.session.commit()
        
    flash('Payment record deleted.', 'info')
    return redirect(url_for('main.lease_detail', id=lease_id))


@main_bp.route('/leases/<int:id>/documents', methods=['POST'])
@login_required
def document_upload(id):
    lease = Lease.query.filter_by(id=id, user_id=g.current_user.id).first_or_404()
    description = request.form.get('description', '').strip()
    
    files = request.files.getlist('document') or request.files.getlist('documents')
    
    if not files or all(f.filename == '' for f in files):
        flash('No file selected.', 'warning')
        return redirect(url_for('main.lease_detail', id=lease.id))
        
    saved_docs = save_multiple_files(files, base_description=description, lease_id=lease.id)
    if saved_docs:
        db.session.commit()
        if len(saved_docs) == 1:
            flash(f'Document "{saved_docs[0].original_filename}" uploaded successfully.', 'success')
        else:
            flash(f'{len(saved_docs)} documents uploaded successfully.', 'success')
    else:
        flash('Invalid file format. Supported: PNG, JPG, JPEG, WEBP, PDF, DOC, DOCX.', 'danger')
        
    return redirect(url_for('main.lease_detail', id=lease.id))


@main_bp.route('/documents/<int:id>/delete', methods=['POST'])
@login_required
def document_delete(id):
    doc = (
        Document.query.join(Lease)
        .filter(Document.id == id, Lease.user_id == g.current_user.id)
        .first_or_404()
    )
    lease_id = doc.lease_id
    filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], doc.filename)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
        except OSError:
            pass
            
    db.session.delete(doc)
    db.session.commit()
    flash('Document deleted.', 'info')
    return redirect(url_for('main.lease_detail', id=lease_id))


@main_bp.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    filename = secure_filename(filename)
    
    # Verify file ownership unless admin or sample file
    if not filename.startswith('sample_'):
        doc = (
            Document.query.join(Lease)
            .filter(Document.filename == filename)
            .first()
        )
        if doc and doc.lease and doc.lease.user_id != g.current_user.id and not g.current_user.is_admin:
            abort(403)

    primary_folder = current_app.config.get('UPLOAD_FOLDER')
    if primary_folder and os.path.exists(os.path.join(primary_folder, filename)):
        return send_from_directory(primary_folder, filename)
        
    fallback_folder = current_app.config.get('FALLBACK_UPLOAD_FOLDER')
    if fallback_folder and os.path.exists(os.path.join(fallback_folder, filename)):
        return send_from_directory(fallback_folder, filename)
        
    return send_from_directory(primary_folder, filename)


# =========================================================
# COUNTERPARTY / PERSON PROFILE ROUTES (SCOPED TO USER)
# =========================================================

@main_bp.route('/parties')
@login_required
def party_list():
    search = request.args.get('search', '').strip()
    query = Counterparty.query.filter_by(user_id=g.current_user.id)
    
    if search:
        query = query.filter(
            (Counterparty.name.ilike(f'%{search}%')) | (Counterparty.phone.ilike(f'%{search}%'))
        )
        
    parties = query.order_by(Counterparty.name.asc()).all()
    return render_template('parties/list.html', parties=parties, search=search)


@main_bp.route('/parties/<int:id>')
@login_required
def party_detail(id):
    party = Counterparty.query.filter_by(id=id, user_id=g.current_user.id).first_or_404()
    
    leases_with_metrics = []
    all_payments = []
    
    for lease in party.leases:
        metrics = calculate_lease_metrics(lease)
        leases_with_metrics.append({
            'lease': lease,
            'metrics': metrics
        })
        for p in lease.payments:
            all_payments.append(p)
            
    all_payments.sort(key=lambda x: (x.payment_date, x.id), reverse=True)
    
    return render_template(
        'parties/detail.html',
        party=party,
        leases_with_metrics=leases_with_metrics,
        all_payments=all_payments,
        today=date.today()
    )


@main_bp.route('/parties/<int:id>/edit', methods=['POST'])
@login_required
def party_edit(id):
    party = Counterparty.query.filter_by(id=id, user_id=g.current_user.id).first_or_404()
    try:
        new_name = request.form.get('name', '').strip()
        if not new_name:
            flash('Person name cannot be empty.', 'danger')
            return redirect(url_for('main.party_detail', id=party.id))
            
        party.name = new_name
        party.phone = request.form.get('phone', '').strip() or None
        party.email = request.form.get('email', '').strip() or None
        party.notes = request.form.get('notes', '').strip() or None
        
        for l in party.leases:
            l.party_name = new_name
            if party.phone:
                l.party_contact = party.phone
                
        db.session.commit()
        flash(f'Profile for "{party.name}" updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating profile: {str(e)}', 'danger')
        
    return redirect(url_for('main.party_detail', id=party.id))


@main_bp.route('/parties/<int:id>/delete', methods=['POST'])
@login_required
def party_delete(id):
    party = Counterparty.query.filter_by(id=id, user_id=g.current_user.id).first_or_404()
    name = party.name
    for l in party.leases:
        l.counterparty_id = None
    db.session.delete(party)
    db.session.commit()
    flash(f'Person profile "{name}" deleted.', 'info')
    return redirect(url_for('main.party_list'))


@main_bp.route('/api/stats')
@login_required
def api_stats():
    leases = Lease.query.filter_by(user_id=g.current_user.id).all()
    payable_paid = sum(l.total_paid for l in leases if l.lease_type == 'payable')
    payable_rem = sum(l.remaining_balance for l in leases if l.lease_type == 'payable')
    receivable_paid = sum(l.total_paid for l in leases if l.lease_type == 'receivable')
    receivable_rem = sum(l.remaining_balance for l in leases if l.lease_type == 'receivable')
    
    return jsonify({
        'payable': {
            'paid': payable_paid,
            'remaining': payable_rem
        },
        'receivable': {
            'collected': receivable_paid,
            'remaining': receivable_rem
        }
    })
