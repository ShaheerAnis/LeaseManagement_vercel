// Lease Management JavaScript Application

document.addEventListener('DOMContentLoaded', () => {
  initModals();
  initLiveCalculator();
  initFileInputs();
  initAlertDismiss();
  initCounterpartyAutofill();
});

// Counterparty Datalist Auto-fill contact info
function initCounterpartyAutofill() {
  const partyInput = document.getElementById('party_name');
  const contactInput = document.getElementById('party_contact');
  const datalist = document.getElementById('counterparty_datalist');

  if (!partyInput || !contactInput || !datalist) return;

  partyInput.addEventListener('input', () => {
    const val = partyInput.value.trim().toLowerCase();
    const options = Array.from(datalist.options);
    const matched = options.find(opt => opt.value.trim().toLowerCase() === val);
    if (matched) {
      const phone = matched.getAttribute('data-phone');
      const email = matched.getAttribute('data-email');
      if (phone) {
        contactInput.value = phone;
      } else if (email && !contactInput.value) {
        contactInput.value = email;
      }
    }
  });
}

// Modal Management
function initModals() {
  // Close buttons
  document.querySelectorAll('.modal-close, [data-dismiss="modal"]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const modal = btn.closest('.modal-backdrop');
      if (modal) closeModal(modal.id);
    });
  });

  // Backdrop click to close
  document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) {
        closeModal(backdrop.id);
      }
    });
  });

  // ESC key to close
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const activeModal = document.querySelector('.modal-backdrop.active');
      if (activeModal) closeModal(activeModal.id);
    }
  });
}

function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove('active');
    document.body.style.overflow = '';
  }
}

// Document Previewer
function previewDocument(url, type, filename) {
  const modal = document.getElementById('docPreviewModal');
  const titleElem = document.getElementById('previewModalTitle');
  const bodyElem = document.getElementById('previewModalBody');
  const downloadLink = document.getElementById('previewDownloadLink');

  if (!modal || !bodyElem) return;

  titleElem.textContent = filename || 'Document Preview';
  downloadLink.href = url;
  downloadLink.setAttribute('download', filename || 'document');

  bodyElem.innerHTML = '';

  if (type === 'image' || url.match(/\.(jpeg|jpg|gif|png|webp)$/i)) {
    const img = document.createElement('img');
    img.src = url;
    img.className = 'preview-img';
    img.alt = filename || 'Preview';
    bodyElem.appendChild(img);
  } else if (type === 'pdf' || url.match(/\.pdf$/i)) {
    const iframe = document.createElement('iframe');
    iframe.src = url;
    iframe.className = 'preview-frame';
    bodyElem.appendChild(iframe);
  } else {
    bodyElem.innerHTML = `
      <div style="text-align: center; color: white; padding: 2rem;">
        <i class="bi bi-file-earmark-arrow-down" style="font-size: 3rem; margin-bottom: 1rem; display: block;"></i>
        <p style="margin-bottom: 1.5rem;">Preview not directly supported in browser for this file type.</p>
        <a href="${url}" class="btn btn-primary" download="${filename}">Download File</a>
      </div>
    `;
  }

  openModal('docPreviewModal');
}

// Live Calculator for Lease Form
function initLiveCalculator() {
  const totalAmountInput = document.getElementById('total_amount');
  const tenureInput = document.getElementById('tenure_months');
  const downPaymentInput = document.getElementById('initial_payment_amount');

  if (!totalAmountInput || !tenureInput) return;

  function calculate() {
    const total = parseFloat(totalAmountInput.value) || 0;
    const tenure = parseInt(tenureInput.value) || 1;
    const downPayment = downPaymentInput ? (parseFloat(downPaymentInput.value) || 0) : 0;

    const remainingBalance = Math.max(0, total - downPayment);
    const standardMonthly = tenure > 0 ? (total / tenure) : 0;
    
    let remainingMonths = tenure;
    if (downPayment > 0) {
      remainingMonths = Math.max(1, tenure - 1);
    }
    const remainingMonthly = remainingMonths > 0 ? (remainingBalance / remainingMonths) : 0;

    const elStandard = document.getElementById('calc_standard_monthly');
    const elRemainingBal = document.getElementById('calc_remaining_balance');
    const elRemainingMonths = document.getElementById('calc_remaining_months');
    const elRemainingMonthly = document.getElementById('calc_remaining_monthly');

    const fmt = (n) => n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

    if (elStandard) elStandard.textContent = fmt(standardMonthly);
    if (elRemainingBal) elRemainingBal.textContent = fmt(remainingBalance);
    if (elRemainingMonths) elRemainingMonths.textContent = remainingMonths + ' mo';
    if (elRemainingMonthly) elRemainingMonthly.textContent = fmt(remainingMonthly);
  }

  totalAmountInput.addEventListener('input', calculate);
  tenureInput.addEventListener('input', calculate);
  if (downPaymentInput) {
    downPaymentInput.addEventListener('input', calculate);
  }

  calculate();
}

// File Input Display Enhancement (Multiple & Single file support)
function initFileInputs() {
  document.querySelectorAll('input[type="file"]').forEach(input => {
    input.addEventListener('change', (e) => {
      const dropzone = input.closest('.file-dropzone');
      if (!dropzone) return;
      const textElem = dropzone.querySelector('.dropzone-text');
      const hintElem = dropzone.querySelector('.dropzone-hint');
      
      // Remove any existing chips container
      const oldChips = dropzone.querySelector('.file-chips-container');
      if (oldChips) oldChips.remove();

      if (input.files && input.files.length > 0) {
        const count = input.files.length;
        let totalSize = 0;
        Array.from(input.files).forEach(f => totalSize += f.size);
        const totalSizeMb = (totalSize / (1024 * 1024)).toFixed(2);

        if (count === 1) {
          const file = input.files[0];
          const sizeMb = (file.size / (1024 * 1024)).toFixed(2);
          if (textElem) textElem.textContent = `Selected: ${file.name}`;
          if (hintElem) hintElem.textContent = `Size: ${sizeMb} MB &bull; Click to change`;
        } else {
          if (textElem) textElem.textContent = `Selected: ${count} documents`;
          if (hintElem) hintElem.textContent = `Total Size: ${totalSizeMb} MB &bull; Click to change or re-select`;
        }

        // Create chip container showing all selected filenames
        const chipsContainer = document.createElement('div');
        chipsContainer.className = 'file-chips-container';

        Array.from(input.files).forEach((file, idx) => {
          const chip = document.createElement('span');
          chip.className = 'file-chip';
          
          let iconClass = 'bi bi-file-earmark';
          if (file.name.match(/\.(jpeg|jpg|png|webp)$/i)) {
            iconClass = 'bi bi-file-earmark-image';
          } else if (file.name.match(/\.pdf$/i)) {
            iconClass = 'bi bi-file-earmark-pdf';
          }
          
          const fSizeKb = (file.size / 1024).toFixed(0);
          chip.innerHTML = `<i class="${iconClass}"></i> <span>${file.name}</span> <small style="opacity:0.75;">(${fSizeKb} KB)</small>`;
          chipsContainer.appendChild(chip);
        });

        dropzone.appendChild(chipsContainer);
        dropzone.style.borderColor = 'var(--primary-600)';
        dropzone.style.background = 'var(--primary-50)';
      }
    });
  });
}

// Alert dismiss
function initAlertDismiss() {
  document.querySelectorAll('.alert-close').forEach(btn => {
    btn.addEventListener('click', () => {
      const alert = btn.closest('.alert');
      if (alert) {
        alert.style.opacity = '0';
        setTimeout(() => alert.remove(), 250);
      }
    });
  });
}
