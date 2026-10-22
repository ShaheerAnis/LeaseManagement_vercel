import os
import unittest
from datetime import date
from app import create_app, db
from app.models import Lease, Payment, Document
from app.calculations import calculate_lease_metrics

class LeaseManagementTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'UPLOAD_FOLDER': '/tmp/lease_test_uploads'
        })
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_mobile_phone_lease_scenario(self):
        """
        User scenario:
        - Mobile phone bought on lease for 12 months.
        - Total amount = 280,000.
        - Month 1 payment = 100,000.
        - Verify remaining balance = 180,000, remaining months = 11, left per month = 16,363.64.
        """
        lease = Lease(
            title="Mobile Phone - iPhone 15 Pro Max",
            lease_type="payable",
            party_name="Tech Store Inc",
            total_amount=280000.0,
            tenure_months=12,
            start_date=date.today(),
            category="Electronics"
        )
        db.session.add(lease)
        db.session.commit()

        # Step 1: Verify Initial
        m1 = calculate_lease_metrics(lease)
        self.assertEqual(m1['total_amount'], 280000.0)
        self.assertEqual(m1['remaining_balance'], 280000.0)
        self.assertEqual(m1['remaining_months'], 12)
        self.assertEqual(m1['remaining_monthly_amount'], 23333.33)

        # Step 2: Record Month 1 payment of 100,000
        payment = Payment(
            lease_id=lease.id,
            amount=100000.0,
            payment_date=date.today(),
            payment_type="down_payment",
            payment_method="Bank Transfer",
            reference_no="TRX-100K-001"
        )
        db.session.add(payment)
        db.session.commit()

        # Step 3: Verify dynamic recalculation
        m2 = calculate_lease_metrics(lease)
        self.assertEqual(m2['total_paid'], 100000.0)
        self.assertEqual(m2['remaining_balance'], 180000.0)
        self.assertEqual(m2['remaining_months'], 11)
        self.assertEqual(m2['remaining_monthly_amount'], 16363.64)

    def test_receivable_lease_scenario(self):
        """
        Give an item on lease (receivable) and collect payments.
        """
        lease = Lease(
            title="Office MacBook Pro",
            lease_type="receivable",
            party_name="Client Sarah",
            total_amount=180000.0,
            tenure_months=6,
            start_date=date.today(),
            category="Electronics"
        )
        db.session.add(lease)
        db.session.commit()

        m = calculate_lease_metrics(lease)
        self.assertEqual(m['remaining_monthly_amount'], 30000.0)

    def test_completed_lease_status_no_due_now(self):
        """
        When a lease status is set to 'completed' (even with 0 or partial recorded payments),
        it must be treated as settled:
        - remaining_balance = 0.0
        - due_status = 'settled' (NEVER 'overdue')
        - is_completed = True
        - schedule unpaid months must be 'waived_settled' (not 'overdue')
        """
        lease = Lease(
            title="Cash Loan",
            lease_type="receivable",
            party_name="Abdul Samad",
            total_amount=20000.0,
            tenure_months=3,
            start_date=date(2026, 7, 1),
            status="completed"
        )
        db.session.add(lease)
        db.session.commit()

        metrics = calculate_lease_metrics(lease)
        self.assertTrue(metrics['is_completed'])
        self.assertEqual(metrics['due_status'], 'settled')
        self.assertEqual(metrics['remaining_balance'], 0.0)
        self.assertEqual(metrics['remaining_monthly_amount'], 0.0)
        self.assertEqual(metrics['remaining_months'], 0)
        for row in metrics['schedule']:
            self.assertIn(row['status'], ('paid', 'waived_settled'))
            self.assertNotEqual(row['status'], 'overdue')

if __name__ == '__main__':
    unittest.main()
