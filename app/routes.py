import os
import uuid
from datetime import datetime, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_from_directory, jsonify, abort
from werkzeug.utils import secure_filename
from app import db
from app.models import Lease, Payment, Document, Counterparty
from app.calculations import calculate_lease_metrics

main_bp = Blueprint('main', __name__)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'pdf', 'doc', 'docx'}

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

def get_or_create_counterparty(name, contact_info=""):
    if not name or not name.strip():
        return None
    cleaned_name = name.strip()
    cp = Counterparty.query.filter(Counterparty.name.ilike(cleaned_name)).first()
    if not cp:
        cp = Counterparty(name=cleaned_name, phone=contact_info.strip() if contact_info else None)
        db.session.add(cp)
        db.session.flush()
    else:
        if contact_info and not cp.phone:
            cp.phone = contact_info.strip()
            db.session.flush()
    return cp


@main_bp.route('/')
def dashboard():
    all_leases = Lease.query.order_by(Lease.created_at.desc()).all()
    
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

    recent_payments = Payment.query.order_by(Payment.payment_date.desc(), Payment.id.desc()).limit(6).all()
    
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
def lease_list():
    lease_type = request.args.get('type', 'all')
    status = request.args.get('status', 'all')
    category = request.args.get('category', 'all')
    search = request.args.get('search', '').strip()
    
    query = Lease.query
    
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
    
    # Get distinct categories for filter
    categories = [r[0] for r in db.session.query(Lease.category).distinct().all() if r[0]]
    
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
def lease_create():
    counterparties = Counterparty.query.order_by(Counterparty.name.asc()).all()
    selected_party_id = request.args.get('party_id')
    preselected_party = db.session.get(Counterparty, int(selected_party_id)) if selected_party_id and selected_party_id.isdigit() else None
    
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
            
            # Find or auto-create Counterparty profile
            cp = get_or_create_counterparty(party_name, party_contact)
            
            lease = Lease(
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
            
            # Check for multiple contract document uploads
            contract_files = request.files.getlist('contract_doc') or request.files.getlist('contract_docs')
            if contract_files:
                save_multiple_files(
                    contract_files,
                    base_description=f"Agreement / Document for {title}",
                    lease_id=lease.id
                )
            
            # Check for initial down payment or first installment
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
                
                # Check for multiple initial receipt uploads
                receipt_files = request.files.getlist('initial_payment_receipt') or request.files.getlist('initial_payment_receipts')
                if receipt_files:
                    save_multiple_files(
                        receipt_files,
                        base_description=f"Receipt for payment of {down_payment_amt:,.2f}",
                        lease_id=lease.id,
                        payment_id=payment.id
                    )
            
            # Auto complete if paid in full
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
def lease_detail(id):
    lease = db.get_or_404(Lease, id)
    metrics = calculate_lease_metrics(lease)
    return render_template('leases/detail.html', lease=lease, metrics=metrics, today=date.today())


@main_bp.route('/leases/<int:id>/edit', methods=['GET', 'POST'])
def lease_edit(id):
    lease = db.get_or_404(Lease, id)
    counterparties = Counterparty.query.order_by(Counterparty.name.asc()).all()
    
    if request.method == 'POST':
        try:
            lease.title = request.form.get('title', '').strip()
            lease.lease_type = request.form.get('lease_type', 'payable')
            party_name = request.form.get('party_name', '').strip()
            party_contact = request.form.get('party_contact', '').strip()
            
            cp = get_or_create_counterparty(party_name, party_contact)
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
def lease_delete(id):
    lease = db.get_or_404(Lease, id)
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
def payment_create(id):
    lease = db.get_or_404(Lease, id)
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
        db.session.flush() # get payment.id
        
        # Check for multiple receipt file uploads
        receipt_files = request.files.getlist('receipt') or request.files.getlist('receipts')
        if receipt_files:
            save_multiple_files(
                receipt_files,
                base_description=f"Receipt for payment of {amount:,.2f} on {p_date}",
                lease_id=lease.id,
                payment_id=payment.id
            )
                
        db.session.commit()
        
        # Check if settled
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
def payment_delete(id):
    payment = db.get_or_404(Payment, id)
    lease_id = payment.lease_id
    
    # Delete uploaded files for this payment
    for doc in payment.documents:
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], doc.filename)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass
                
    db.session.delete(payment)
    db.session.commit()
    
    # If lease was marked completed, reactivate if balance remains
    lease = db.session.get(Lease, lease_id)
    if lease and lease.status == 'completed' and lease.remaining_balance > 0.001:
        lease.status = 'active'
        db.session.commit()
        
    flash('Payment record deleted.', 'info')
    return redirect(url_for('main.lease_detail', id=lease_id))


@main_bp.route('/leases/<int:id>/documents', methods=['POST'])
def document_upload(id):
    lease = db.get_or_404(Lease, id)
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
def document_delete(id):
    doc = db.get_or_404(Document, id)
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
def uploaded_file(filename):
    filename = secure_filename(filename)
    primary_folder = current_app.config.get('UPLOAD_FOLDER')
    if primary_folder and os.path.exists(os.path.join(primary_folder, filename)):
        return send_from_directory(primary_folder, filename)
        
    fallback_folder = current_app.config.get('FALLBACK_UPLOAD_FOLDER')
    if fallback_folder and os.path.exists(os.path.join(fallback_folder, filename)):
        return send_from_directory(fallback_folder, filename)
        
    return send_from_directory(primary_folder, filename)


# =========================================================
# COUNTERPARTY / PERSON PROFILE ROUTES
# =========================================================

@main_bp.route('/parties')
def party_list():
    search = request.args.get('search', '').strip()
    query = Counterparty.query
    
    if search:
        query = query.filter(
            (Counterparty.name.ilike(f'%{search}%')) | (Counterparty.phone.ilike(f'%{search}%'))
        )
        
    parties = query.order_by(Counterparty.name.asc()).all()
    
    # Backfill/sync any leases that might have string party_name without counterparty_id
    # so every person shows up in profiles!
    return render_template('parties/list.html', parties=parties, search=search)


@main_bp.route('/parties/<int:id>')
def party_detail(id):
    party = db.get_or_404(Counterparty, id)
    
    # All leases with this party with their metrics
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
def party_edit(id):
    party = db.get_or_404(Counterparty, id)
    try:
        new_name = request.form.get('name', '').strip()
        if not new_name:
            flash('Person name cannot be empty.', 'danger')
            return redirect(url_for('main.party_detail', id=party.id))
            
        party.name = new_name
        party.phone = request.form.get('phone', '').strip() or None
        party.email = request.form.get('email', '').strip() or None
        party.notes = request.form.get('notes', '').strip() or None
        
        # Sync lease.party_name for all associated leases
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
def party_delete(id):
    party = db.get_or_404(Counterparty, id)
    name = party.name
    # Unlink from leases before deleting party
    for l in party.leases:
        l.counterparty_id = None
    db.session.delete(party)
    db.session.commit()
    flash(f'Person profile "{name}" deleted.', 'info')
    return redirect(url_for('main.party_list'))


@main_bp.route('/api/stats')
def api_stats():
    leases = Lease.query.all()
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
