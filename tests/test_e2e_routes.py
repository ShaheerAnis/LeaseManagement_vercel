import os
import io
import unittest
from datetime import date
from app import create_app, db
from app.models import Lease, Payment, Document

class LeaseRoutesTestCase(unittest.TestCase):
    def setUp(self):
        self.upload_dir = '/tmp/lease_test_uploads_routes'
        os.makedirs(self.upload_dir, exist_ok=True)
        
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'UPLOAD_FOLDER': self.upload_dir
        })
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_dashboard_and_list_empty(self):
        res = self.client.get('/')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Financial Overview', res.data)

        res_list = self.client.get('/leases')
        self.assertEqual(res_list.status_code, 200)
        self.assertIn(b'No matching leases found', res_list.data)

    def test_create_lease_and_record_payment_flow(self):
        # 1. Create a lease via POST
        data = {
            'title': 'Samsung Galaxy S24 Ultra',
            'lease_type': 'payable',
            'party_name': 'Samsung Official Store',
            'party_contact': '0300-1122334',
            'total_amount': '240000',
            'tenure_months': '12',
            'start_date': str(date.today()),
            'category': 'Electronics',
            'notes': 'Test notes',
            'initial_payment_amount': '60000',
            'initial_payment_date': str(date.today()),
            'initial_payment_method': 'Bank Transfer',
            'initial_payment_ref': 'INIT-TRX-101',
            'initial_payment_type': 'down_payment'
        }
        res = self.client.post('/leases/new', data=data, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Samsung Galaxy S24 Ultra', res.data)
        
        # Verify calculation in response
        self.assertIn(b'16,363.64', res.data)
        self.assertIn(b'180,000.00', res.data)

        # 2. Record next month payment with a fake receipt file
        lease = Lease.query.first()
        payment_data = {
            'amount': '16363.64',
            'payment_date': str(date.today()),
            'payment_type': 'installment',
            'payment_method': 'Cash',
            'reference_no': 'REC-002',
            'receipt': (io.BytesIO(b'Fake receipt image content'), 'receipt_m2.png')
        }
        res_pay = self.client.post(f'/leases/{lease.id}/payments', data=payment_data, follow_redirects=True, content_type='multipart/form-data')
        self.assertEqual(res_pay.status_code, 200)
        self.assertIn(b'successfully recorded', res_pay.data)

        # Verify new remaining balance: 240000 - 76363.64 = 163636.36
        self.assertIn(b'163,636.36', res_pay.data)

        # 3. Test single document upload
        doc_data = {
            'description': 'Signed Warranty Card',
            'document': (io.BytesIO(b'Fake PDF content'), 'warranty_agreement.pdf')
        }
        res_doc = self.client.post(f'/leases/{lease.id}/documents', data=doc_data, follow_redirects=True, content_type='multipart/form-data')
        self.assertEqual(res_doc.status_code, 200)
        self.assertIn(b'Signed Warranty Card', res_doc.data)

    def test_multiple_documents_upload_flow(self):
        # 1. Create lease with multiple contract documents and multiple initial receipts
        data = {
            'title': 'MacBook Pro Setup',
            'lease_type': 'payable',
            'party_name': 'Tech Hub',
            'total_amount': '300000',
            'tenure_months': '10',
            'start_date': str(date.today()),
            'initial_payment_amount': '50000',
            'contract_doc': [
                (io.BytesIO(b'Contract page 1'), 'contract_p1.pdf'),
                (io.BytesIO(b'Contract page 2'), 'contract_p2.pdf')
            ],
            'initial_payment_receipt': [
                (io.BytesIO(b'Slip 1'), 'bank_slip_1.png'),
                (io.BytesIO(b'Slip 2'), 'bank_slip_2.jpg')
            ]
        }
        res = self.client.post('/leases/new', data=data, follow_redirects=True, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 200)
        
        lease = Lease.query.filter_by(title='MacBook Pro Setup').first()
        self.assertIsNotNone(lease)
        
        # Verify 4 documents were stored in total (2 for lease contracts, 2 for payment receipts)
        self.assertEqual(len(lease.documents), 4)

        # 2. Upload 3 more documents at once via lease detail modal
        multi_doc_data = {
            'description': 'Additional Proofs',
            'document': [
                (io.BytesIO(b'Doc A'), 'id_card.png'),
                (io.BytesIO(b'Doc B'), 'guarantor_form.pdf'),
                (io.BytesIO(b'Doc C'), 'delivery_challan.pdf')
            ]
        }
        res_multi = self.client.post(f'/leases/{lease.id}/documents', data=multi_doc_data, follow_redirects=True, content_type='multipart/form-data')
        self.assertEqual(res_multi.status_code, 200)
        self.assertIn(b'3 documents uploaded successfully', res_multi.data)
        
        self.assertEqual(len(lease.documents), 7)

if __name__ == '__main__':
    unittest.main()
