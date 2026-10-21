import os
import shutil
from datetime import date, timedelta, datetime, timezone
from app import create_app, db
from app.models import Lease, Payment, Document, User, Counterparty

def seed_database():
    app = create_app()
    with app.app_context():
        # Clear existing tables
        db.drop_all()
        db.create_all()

        # Create Admin user Shaheer Anis
        shaheer = User(
            username="shaheer.anis",
            full_name="Shaheer Anis",
            email="shaheer.anis@leaseflow.io",
            role="admin",
            status="approved",
            approved_at=datetime.now(timezone.utc)
        )
        shaheer.set_password("shaheer.1anis")
        db.session.add(shaheer)
        db.session.flush()

        upload_dir = app.config['UPLOAD_FOLDER']
        os.makedirs(upload_dir, exist_ok=True)

        # Create a sample receipt file
        sample_receipt_filename = "sample_receipt_100k.png"
        sample_receipt_path = os.path.join(upload_dir, sample_receipt_filename)
        
        with open(sample_receipt_path, 'wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82')

        # 1. Counterparty: Mega Electronics Store
        cp1 = Counterparty(
            user_id=shaheer.id,
            name="Mega Electronics Store",
            phone="+92 300 1234567",
            email="info@megaelectronics.com"
        )
        db.session.add(cp1)
        db.session.flush()

        # 1. User's specific scenario: Mobile Phone on Lease (Payable)
        iphone_lease = Lease(
            user_id=shaheer.id,
            counterparty_id=cp1.id,
            title="Mobile Phone - iPhone 15 Pro",
            lease_type="payable",
            party_name=cp1.name,
            party_contact=cp1.phone,
            total_amount=280000.0,
            tenure_months=12,
            start_date=date.today() - timedelta(days=25),
            category="Electronics",
            status="active",
            notes="12-month installment plan. First month down payment of 100,000 paid."
        )
        db.session.add(iphone_lease)
        db.session.flush()

        payment1 = Payment(
            lease_id=iphone_lease.id,
            amount=100000.0,
            payment_date=date.today() - timedelta(days=25),
            payment_type="down_payment",
            payment_method="Bank Transfer",
            reference_no="TRX-998822",
            notes="Month 1 upfront payment"
        )
        db.session.add(payment1)
        db.session.flush()

        doc1 = Document(
            lease_id=iphone_lease.id,
            payment_id=payment1.id,
            filename=sample_receipt_filename,
            original_filename="HBL_Bank_Slip_100000.png",
            file_type="image",
            file_size=os.path.getsize(sample_receipt_path),
            description="Bank transfer receipt for 100,000 PKR down payment"
        )
        db.session.add(doc1)

        # 2. Counterparty: Apex Media Studio
        cp2 = Counterparty(
            user_id=shaheer.id,
            name="Apex Media Studio (Kamran)",
            phone="+92 321 7654321"
        )
        db.session.add(cp2)
        db.session.flush()

        # 2. Receivable lease: Leased out MacBook Pro
        macbook_lease = Lease(
            user_id=shaheer.id,
            counterparty_id=cp2.id,
            title="MacBook Pro M3 Max",
            lease_type="receivable",
            party_name=cp2.name,
            party_contact=cp2.phone,
            total_amount=360000.0,
            tenure_months=6,
            start_date=date.today() - timedelta(days=60),
            category="Electronics",
            status="active",
            notes="Rented out workstation for video editing team."
        )
        db.session.add(macbook_lease)
        db.session.flush()

        p_mac1 = Payment(
            lease_id=macbook_lease.id,
            amount=60000.0,
            payment_date=date.today() - timedelta(days=58),
            payment_type="installment",
            payment_method="Online",
            reference_no="PAY-M1-881",
            notes="Month 1 installment received"
        )
        p_mac2 = Payment(
            lease_id=macbook_lease.id,
            amount=60000.0,
            payment_date=date.today() - timedelta(days=28),
            payment_type="installment",
            payment_method="Online",
            reference_no="PAY-M2-993",
            notes="Month 2 installment received"
        )
        db.session.add_all([p_mac1, p_mac2])

        # 3. Counterparty: Bank Al Habib Auto Finance
        cp3 = Counterparty(
            user_id=shaheer.id,
            name="Bank Al Habib Auto Finance",
            phone="021-111-014-014"
        )
        db.session.add(cp3)
        db.session.flush()

        # 3. Vehicle Lease (Payable)
        car_lease = Lease(
            user_id=shaheer.id,
            counterparty_id=cp3.id,
            title="Honda Civic 2024",
            lease_type="payable",
            party_name=cp3.name,
            party_contact=cp3.phone,
            total_amount=4800000.0,
            tenure_months=36,
            start_date=date.today() - timedelta(days=90),
            category="Vehicles",
            status="active",
            notes="Auto lease agreement with fixed monthly markup."
        )
        db.session.add(car_lease)
        db.session.flush()

        p_car1 = Payment(
            lease_id=car_lease.id,
            amount=1200000.0,
            payment_date=date.today() - timedelta(days=90),
            payment_type="down_payment",
            payment_method="Bank Transfer",
            reference_no="CHQ-009182",
            notes="25% Down payment at delivery"
        )
        p_car2 = Payment(
            lease_id=car_lease.id,
            amount=100000.0,
            payment_date=date.today() - timedelta(days=60),
            payment_type="installment",
            payment_method="Direct Debit",
            reference_no="AUTOPAY-01",
            notes="Installment 1"
        )
        p_car3 = Payment(
            lease_id=car_lease.id,
            amount=100000.0,
            payment_date=date.today() - timedelta(days=30),
            payment_type="installment",
            payment_method="Direct Debit",
            reference_no="AUTOPAY-02",
            notes="Installment 2"
        )
        db.session.add_all([p_car1, p_car2, p_car3])

        db.session.commit()
        print("Database seeded with admin user 'shaheer.anis' and sample leases successfully!")

if __name__ == '__main__':
    seed_database()
