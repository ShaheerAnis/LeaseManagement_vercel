import unittest
from datetime import date
from app import create_app, db
from app.models import Lease, Payment, Counterparty

class CounterpartyTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'UPLOAD_FOLDER': '/tmp/test_counterparty_uploads'
        })
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        
        from app.models import User
        self.admin = User.query.filter_by(username='shaheer.anis').first()
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.admin.id

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_counterparty_auto_creation_and_reuse(self):
        # 1. Create first deal: Gave Saqib 5,000 PKR (Receivable)
        res1 = self.client.post('/leases/new', data={
            'title': 'Cash Loan',
            'lease_type': 'receivable',
            'party_name': 'Saqib Ur Rehman',
            'party_contact': '+92 300 5555555',
            'total_amount': '5000',
            'tenure_months': '2',
            'start_date': str(date.today()),
            'category': 'Personal'
        }, follow_redirects=True)
        self.assertEqual(res1.status_code, 200)

        # Verify Counterparty was created
        saqib = Counterparty.query.filter_by(name='Saqib Ur Rehman').first()
        self.assertIsNotNone(saqib)
        self.assertEqual(saqib.phone, '+92 300 5555555')
        self.assertEqual(saqib.total_receivable_balance, 5000.0)
        self.assertEqual(saqib.total_payable_balance, 0.0)
        self.assertEqual(saqib.net_balance, 5000.0)

        # 2. Create second deal: Took 2,000 PKR from Saqib (Payable / I owe)
        res2 = self.client.post('/leases/new', data={
            'title': 'Borrowed Cash',
            'lease_type': 'payable',
            'party_name': 'Saqib Ur Rehman',  # Existing name chosen from dropdown
            'party_contact': '+92 300 5555555',
            'total_amount': '2000',
            'tenure_months': '1',
            'start_date': str(date.today()),
            'category': 'Personal'
        }, follow_redirects=True)
        self.assertEqual(res2.status_code, 200)

        # Verify only 1 Saqib exists with both leases linked
        all_saqibs = Counterparty.query.filter_by(name='Saqib Ur Rehman').all()
        self.assertEqual(len(all_saqibs), 1)
        self.assertEqual(len(saqib.leases), 2)

        # Net balance: 5,000 (receivable) - 2,000 (payable) = +3,000 net owed to user
        self.assertEqual(saqib.total_receivable_balance, 5000.0)
        self.assertEqual(saqib.total_payable_balance, 2000.0)
        self.assertEqual(saqib.net_balance, 3000.0)

        # 3. View Profile Page
        res_profile = self.client.get(f'/parties/{saqib.id}')
        self.assertEqual(res_profile.status_code, 200)
        self.assertIn(b'Saqib Ur Rehman', res_profile.data)
        self.assertIn(b'3,000.00', res_profile.data)
        self.assertIn(b'Cash Loan', res_profile.data)
        self.assertIn(b'Borrowed Cash', res_profile.data)

        # 4. View Parties Directory
        res_parties = self.client.get('/parties')
        self.assertEqual(res_parties.status_code, 200)
        self.assertIn(b'Saqib Ur Rehman', res_parties.data)

    def test_party_profile_edit(self):
        # Create party
        party = Counterparty(name='Asfand Barki', phone='0300-1234567', user_id=self.admin.id)
        db.session.add(party)
        db.session.commit()

        # Edit profile
        res_edit = self.client.post(f'/parties/{party.id}/edit', data={
            'name': 'Asfand Barki (Senior)',
            'phone': '0300-9999999',
            'email': 'asfand@example.com',
            'notes': 'Reliable client'
        }, follow_redirects=True)
        self.assertEqual(res_edit.status_code, 200)

        updated = db.session.get(Counterparty, party.id)
        self.assertEqual(updated.name, 'Asfand Barki (Senior)')
        self.assertEqual(updated.phone, '0300-9999999')
        self.assertEqual(updated.email, 'asfand@example.com')
        self.assertEqual(updated.notes, 'Reliable client')

if __name__ == '__main__':
    unittest.main()
