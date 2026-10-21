# LeaseFlow - Smart Lease Management Flask Application

A modern, full-featured web application designed to track and manage personal and business leases—both items **bought on lease** (*Leases Payable*) and items **given on lease** (*Leases Receivable*).

---

## 🌟 Key Features

1. **Dual-Track Lease Management**:
   - **Payable (I Owe)**: Track items bought on installments (e.g. mobile phones, cars, electronics, appliances).
   - **Receivable (I Collect)**: Track items leased out to customers or clients with monthly income tracking.
2. **Dynamic Installment Recalculation**:
   - As down payments, early payoffs, or irregular lump sums are recorded, the app dynamically recalculates the exact amount remaining **per month** across the remaining tenure months.
   - *Example*: Total 280,000 PKR for 12 months. Month 1 payment of 100,000 PKR $\to$ automatically updates remaining balance to 180,000 PKR and remaining monthly payment to **16,363.64 PKR / month** across the 11 remaining months.
3. **Proof of Payment & Document Management**:
   - Upload receipt screenshots (PNG, JPG, WEBP) or PDF documents as proof for each payment.
   - Attach signed contracts, agreements, or warranty cards directly to any lease.
   - In-browser interactive preview modal for images and PDFs.
4. **Interactive Dashboard & Financial Overview**:
   - Real-time stat cards: Total Payable Balance, Total Receivable Balance, Monthly Net Commitments, and Active Leases.
   - Filter portfolio by status (*Active*, *Completed*, *Cancelled*), direction (*Payable*, *Receivable*), category, or keyword search.
5. **Month-by-Month Installment Schedule**:
   - Visual timeline displaying past cleared payments with receipts, upcoming dues, and overdue alerts.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.10+
- `venv` (standard in Python 3)

### 2. Activate Virtual Environment & Run
```bash
# Activate virtual environment
source venv/bin/activate

# (Optional) Seed sample data
python seed.py

# Start the Flask application
python run.py
```

Open your browser and navigate to:
```
http://127.0.0.1:5001
```

---

## 🧪 Running Automated Tests

Run the test suite using Python's built-in `unittest` runner:
```bash
./venv/bin/python -m unittest discover -s tests
```

---

## 📁 Project Structure

```
LeaseManagement/
├── app/
│   ├── __init__.py          # Flask app factory, custom Jinja filters
│   ├── models.py            # Lease, Payment, Document SQLAlchemy models
│   ├── routes.py            # Dashboard, CRUD views, payment & upload handlers
│   ├── calculations.py      # Dynamic recalculation engine & schedule projection
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css    # Modern UI design system
│   │   ├── js/
│   │   │   └── app.js       # Modals, live calculator, preview handlers
│   │   └── uploads/         # Uploaded receipts & contract documents
│   └── templates/
│       ├── base.html        # Main layout, navbar, preview modal
│       ├── dashboard.html   # KPI stat cards, recent payments, overview
│       └── leases/
│           ├── list.html    # Filterable portfolio directory
│           ├── detail.html  # Detail view, monthly schedule & payment history
│           └── form.html    # Create/Edit form with live monthly estimator
├── instance/
│   └── lease_management.db  # SQLite database
├── tests/
│   ├── test_lease_flow.py   # Unit tests for calculations & scenarios
│   └── test_e2e_routes.py   # Integration tests for routes & file uploads
├── requirements.txt         # Project dependencies
├── run.py                   # App entrypoint (runs on port 5001)
├── seed.py                  # Sample data loader
└── README.md
```
