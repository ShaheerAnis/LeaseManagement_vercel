import os
import unittest
from datetime import date
from app import create_app, db
from app.models import User, Lease, Counterparty

class AuthenticationAndMultiTenancyTestCase(unittest.TestCase):
    def setUp(self):
        self.upload_dir = '/tmp/lease_test_uploads_auth'
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

    def test_default_admin_credentials_and_login(self):
        """Verify shaheer.anis exists with role admin, approved, and correct password."""
        admin = User.query.filter_by(username='shaheer.anis').first()
        self.assertIsNotNone(admin)
        self.assertEqual(admin.role, 'admin')
        self.assertEqual(admin.status, 'approved')
        self.assertTrue(admin.check_password('shaheer.1anis'))

        # Log in via POST /login
        res = self.client.post('/login', data={
            'username': 'shaheer.anis',
            'password': 'shaheer.1anis'
        }, follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Welcome back, Shaheer Anis', res.data)

    def test_signup_creates_pending_user_and_blocks_login(self):
        """New users must be pending approval and cannot log in until approved."""
        res_signup = self.client.post('/signup', data={
            'username': 'ali.raza',
            'full_name': 'Ali Raza',
            'email': 'ali@example.com',
            'password': 'Password123!',
            'confirm_password': 'Password123!'
        }, follow_redirects=True)
        self.assertEqual(res_signup.status_code, 200)
        self.assertIn(b'PENDING approval', res_signup.data)

        # Verify record in database
        user = User.query.filter_by(username='ali.raza').first()
        self.assertIsNotNone(user)
        self.assertEqual(user.status, 'pending')
        self.assertEqual(user.role, 'user')
        self.assertFalse(user.is_approved)

        # Attempt login before approval -> Must be blocked
        res_login = self.client.post('/login', data={
            'username': 'ali.raza',
            'password': 'Password123!'
        }, follow_redirects=True)
        self.assertEqual(res_login.status_code, 200)
        self.assertIn(b'awaiting approval by the administrator', res_login.data)

        # Attempt to access dashboard without valid approved session -> Must redirect to login
        res_dash = self.client.get('/')
        self.assertEqual(res_dash.status_code, 302)
        self.assertIn('/login', res_dash.headers['Location'])

    def test_admin_approval_flow_and_subsequent_login(self):
        """Admin can review pending users, approve them, and they can then log in."""
        # 1. Create a user via signup
        self.client.post('/signup', data={
            'username': 'bilal.khan',
            'full_name': 'Bilal Khan',
            'password': 'BilalPassword123',
            'confirm_password': 'BilalPassword123'
        }, follow_redirects=True)

        user = User.query.filter_by(username='bilal.khan').first()

        # 2. Admin logs in
        admin = User.query.filter_by(username='shaheer.anis').first()
        with self.client.session_transaction() as sess:
            sess['user_id'] = admin.id

        # 3. Admin visits /admin/users
        res_admin = self.client.get('/admin/users')
        self.assertEqual(res_admin.status_code, 200)
        self.assertIn(b'bilal.khan', res_admin.data)
        self.assertIn(b'Pending Approval', res_admin.data)

        # 4. Admin approves user
        res_approve = self.client.post(f'/admin/users/{user.id}/approve', follow_redirects=True)
        self.assertEqual(res_approve.status_code, 200)
        self.assertIn(b'has been APPROVED', res_approve.data)

        user_reloaded = db.session.get(User, user.id)
        self.assertEqual(user_reloaded.status, 'approved')
        self.assertTrue(user_reloaded.is_approved)

        # 5. Clear session and log in as Bilal
        with self.client.session_transaction() as sess:
            sess.clear()

        res_bilal_login = self.client.post('/login', data={
            'username': 'bilal.khan',
            'password': 'BilalPassword123'
        }, follow_redirects=True)
        self.assertEqual(res_bilal_login.status_code, 200)
        self.assertIn(b'Welcome back, Bilal Khan', res_bilal_login.data)

    def test_multi_tenant_data_isolation(self):
        """User A and User B cannot see each other's leases, counterparties, or payments."""
        admin = User.query.filter_by(username='shaheer.anis').first()

        # Create approved user Zaid
        zaid = User(
            username='zaid.hassan',
            full_name='Zaid Hassan',
            role='user',
            status='approved'
        )
        zaid.set_password('ZaidPassword123')
        db.session.add(zaid)
        db.session.commit()

        # Create lease for Admin (Shaheer)
        admin_lease = Lease(
            user_id=admin.id,
            title='Admin iPhone 16 Pro',
            lease_type='payable',
            party_name='Apple Store',
            total_amount=300000.0,
            tenure_months=12,
            start_date=date.today(),
            category='Electronics'
        )
        db.session.add(admin_lease)

        # Create lease for Zaid
        zaid_lease = Lease(
            user_id=zaid.id,
            title='Zaid Honda 125 Bike',
            lease_type='payable',
            party_name='Honda Showroom',
            total_amount=150000.0,
            tenure_months=10,
            start_date=date.today(),
            category='Vehicles'
        )
        db.session.add(zaid_lease)
        db.session.commit()

        # 1. Log in as Zaid
        with self.client.session_transaction() as sess:
            sess['user_id'] = zaid.id

        # Zaid's dashboard must only show Zaid's lease
        res_zaid_dash = self.client.get('/')
        self.assertEqual(res_zaid_dash.status_code, 200)
        self.assertIn(b'Zaid Honda 125 Bike', res_zaid_dash.data)
        self.assertNotIn(b'Admin iPhone 16 Pro', res_zaid_dash.data)

        # Zaid's leases list must only contain Zaid's lease
        res_zaid_list = self.client.get('/leases')
        self.assertEqual(res_zaid_list.status_code, 200)
        self.assertIn(b'Zaid Honda 125 Bike', res_zaid_list.data)
        self.assertNotIn(b'Admin iPhone 16 Pro', res_zaid_list.data)

        # Zaid cannot view Admin's lease detail -> 404
        res_forbidden = self.client.get(f'/leases/{admin_lease.id}')
        self.assertEqual(res_forbidden.status_code, 404)

        # 2. Log in as Admin (Shaheer)
        with self.client.session_transaction() as sess:
            sess['user_id'] = admin.id

        # Admin dashboard only shows Admin's leases
        res_admin_dash = self.client.get('/')
        self.assertEqual(res_admin_dash.status_code, 200)
        self.assertIn(b'Admin iPhone 16 Pro', res_admin_dash.data)
        self.assertNotIn(b'Zaid Honda 125 Bike', res_admin_dash.data)

        # Admin cannot access Zaid's lease detail via standard route
        res_admin_zaid = self.client.get(f'/leases/{zaid_lease.id}')
        self.assertEqual(res_admin_zaid.status_code, 404)

    def test_admin_route_protection_against_regular_users(self):
        """Standard users cannot access admin user management routes."""
        user = User(
            username='regular.user',
            full_name='Regular User',
            role='user',
            status='approved'
        )
        user.set_password('UserPassword123')
        db.session.add(user)
        db.session.commit()

        # Log in as regular user
        with self.client.session_transaction() as sess:
            sess['user_id'] = user.id

        # Attempt to access /admin/users -> Redirected with danger alert
        res = self.client.get('/admin/users', follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'Administrator privileges are required', res.data)

if __name__ == '__main__':
    unittest.main()
