from datetime import date, datetime
from dateutil.relativedelta import relativedelta

def add_months(source_date, months):
    """Safely adds months to a date, preserving day of month when possible."""
    return source_date + relativedelta(months=months)

def calculate_lease_metrics(lease):
    """
    Computes dynamic financial and schedule metrics for a lease.
    
    Example:
    Total Amount: 280,000
    Tenure: 12 months
    Month 1 Paid: 100,000
    -> Remaining Balance: 180,000
    -> Remaining Months: 11
    -> Remaining Per Month: 16,363.64
    """
    total_amount = float(lease.total_amount)
    tenure_months = max(1, int(lease.tenure_months))
    start_date = lease.start_date
    today = date.today()
    
    # Payments summary
    payments = lease.payments
    total_paid = sum(p.amount for p in payments)
    remaining_balance = max(0.0, round(total_amount - total_paid, 2))
    
    # Progress percentage
    progress_pct = round((total_paid / total_amount * 100), 1) if total_amount > 0 else 100.0
    progress_pct = min(100.0, max(0.0, progress_pct))
    
    # Original monthly installment
    original_monthly_installment = round(total_amount / tenure_months, 2)
    
    # Calendar elapsed months since start date
    months_difference = (today.year - start_date.year) * 12 + (today.month - start_date.month)
    elapsed_months = max(0, min(tenure_months, months_difference))
    
    # Count of payments made
    payments_count = len(payments)
    
    # Remaining months calculation:
    if remaining_balance <= 0.001:
        is_completed = True
        effective_remaining_months = 0
        remaining_monthly_amount = 0.0
    else:
        is_completed = False
        if payments_count == 0:
            effective_remaining_months = tenure_months
        else:
            effective_remaining_months = max(1, tenure_months - payments_count)
            
        remaining_monthly_amount = round(remaining_balance / effective_remaining_months, 2)
        
    # Projected end date
    projected_end_date = add_months(start_date, tenure_months)
    
    # Next upcoming due date
    if is_completed:
        next_due_date = None
        due_status = 'settled'
    else:
        target_cycle = min(tenure_months - 1, payments_count)
        next_due_date = add_months(start_date, target_cycle)
        if next_due_date < today:
            due_status = 'overdue'
        elif next_due_date <= add_months(today, 1):
            due_status = 'due_soon'
        else:
            due_status = 'on_track'

    # Build monthly schedule timeline
    schedule = []
    accumulated_paid = 0.0
    
    for i in range(1, tenure_months + 1):
        month_due_date = add_months(start_date, i - 1)
        
        # Check if there is a matching payment for this installment index
        matching_payment = payments[i - 1] if (i - 1) < len(payments) else None
        
        if matching_payment:
            paid_amount = matching_payment.amount
            accumulated_paid += paid_amount
            status = 'paid'
            receipt_doc = matching_payment.documents[0] if matching_payment.documents else None
        else:
            paid_amount = 0.0
            receipt_doc = None
            if remaining_balance <= 0.001:
                status = 'waived_settled'
            elif month_due_date < today:
                status = 'overdue'
            elif month_due_date <= add_months(today, 1):
                status = 'upcoming'
            else:
                status = 'future'
                
        schedule.append({
            'month_num': i,
            'due_date': month_due_date,
            'expected_amount': remaining_monthly_amount if not matching_payment else matching_payment.amount,
            'original_expected': original_monthly_installment,
            'actual_paid': paid_amount,
            'payment': matching_payment,
            'receipt_doc': receipt_doc,
            'status': status
        })

    return {
        'total_amount': total_amount,
        'total_paid': total_paid,
        'remaining_balance': remaining_balance,
        'progress_pct': progress_pct,
        'original_monthly_installment': original_monthly_installment,
        'remaining_months': effective_remaining_months,
        'remaining_monthly_amount': remaining_monthly_amount,
        'elapsed_months': elapsed_months,
        'tenure_months': tenure_months,
        'is_completed': is_completed,
        'next_due_date': next_due_date,
        'due_status': due_status,
        'projected_end_date': projected_end_date,
        'payments_count': payments_count,
        'schedule': schedule
    }
