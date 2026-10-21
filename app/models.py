from datetime import datetime, timezone, date
from app import db

def utc_now():
    return datetime.now(timezone.utc)

class Counterparty(db.Model):
    __tablename__ = 'counterparties'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    phone = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    # Relationships
    leases = db.relationship('Lease', backref='counterparty', lazy=True, order_by='Lease.created_at.desc()')

    def __repr__(self):
        return f"<Counterparty {self.id}: {self.name}>"

    @property
    def total_payable_balance(self):
        """Total money I owe to this person on active leases."""
        return sum(l.remaining_balance for l in self.leases if l.lease_type == 'payable' and l.status == 'active')

    @property
    def total_receivable_balance(self):
        """Total money this person owes me on active leases."""
        return sum(l.remaining_balance for l in self.leases if l.lease_type == 'receivable' and l.status == 'active')

    @property
    def net_balance(self):
        """Net balance (positive means they owe me, negative means I owe them)."""
        return self.total_receivable_balance - self.total_payable_balance

    @property
    def active_leases_count(self):
        return sum(1 for l in self.leases if l.status == 'active')


class Lease(db.Model):
    __tablename__ = 'leases'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    lease_type = db.Column(db.String(20), nullable=False, default='payable') # 'payable' (I owe / bought) or 'receivable' (I gave / receive)
    counterparty_id = db.Column(db.Integer, db.ForeignKey('counterparties.id', ondelete='SET NULL'), nullable=True)
    party_name = db.Column(db.String(120), nullable=False) # Vendor or Customer Name
    party_contact = db.Column(db.String(120), nullable=True) # Phone / Email
    total_amount = db.Column(db.Float, nullable=False)
    tenure_months = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date, nullable=False, default=date.today)
    category = db.Column(db.String(50), nullable=False, default='Electronics')
    status = db.Column(db.String(20), nullable=False, default='active') # 'active', 'completed', 'cancelled'
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
    
    # Relationships
    payments = db.relationship('Payment', backref='lease', cascade='all, delete-orphan', lazy=True, order_by='Payment.payment_date.asc(), Payment.id.asc()')
    documents = db.relationship('Document', backref='lease', cascade='all, delete-orphan', lazy=True, order_by='Document.uploaded_at.desc()')

    def __repr__(self):
        return f"<Lease {self.id}: {self.title} ({self.lease_type})>"

    @property
    def total_paid(self):
        return sum(p.amount for p in self.payments)

    @property
    def remaining_balance(self):
        return max(0.0, self.total_amount - self.total_paid)

    @property
    def is_settled(self):
        return self.remaining_balance <= 0.001


class Payment(db.Model):
    __tablename__ = 'payments'
    
    id = db.Column(db.Integer, primary_key=True)
    lease_id = db.Column(db.Integer, db.ForeignKey('leases.id', ondelete='CASCADE'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.Date, nullable=False, default=date.today)
    payment_type = db.Column(db.String(30), nullable=False, default='installment') # 'down_payment', 'installment', 'lump_sum', 'settlement'
    payment_method = db.Column(db.String(50), nullable=False, default='Bank Transfer') # 'Bank Transfer', 'Cash', 'Card', 'Cheque', 'Online'
    reference_no = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=utc_now)
    
    # Relationships
    documents = db.relationship('Document', backref='payment', cascade='all, delete-orphan', lazy=True)

    def __repr__(self):
        return f"<Payment {self.id}: {self.amount} for Lease {self.lease_id}>"


class Document(db.Model):
    __tablename__ = 'documents'
    
    id = db.Column(db.Integer, primary_key=True)
    lease_id = db.Column(db.Integer, db.ForeignKey('leases.id', ondelete='CASCADE'), nullable=True)
    payment_id = db.Column(db.Integer, db.ForeignKey('payments.id', ondelete='CASCADE'), nullable=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(20), nullable=False) # 'image', 'pdf', 'document'
    file_size = db.Column(db.Integer, nullable=False) # size in bytes
    description = db.Column(db.String(255), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=utc_now)

    def __repr__(self):
        return f"<Document {self.id}: {self.original_filename}>"
