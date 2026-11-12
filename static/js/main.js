// ===================================
// Modern PDF Extractor - Main Script
// ===================================

// Build the copy text from the table, in the order currently shown.
// Every cell is kept (empty separator columns included) joined by tabs.
function tableToText() {
    const rows = document.querySelectorAll('#results-table tbody tr');
    return Array.from(rows).map(function (tr) {
        return Array.from(tr.cells).map(function (td) {
            return td.textContent.trim();
        }).join('\t');
    }).join('\n');
}

// Sort rows by reference (first column) in natural order: A2 before A10.
// Whole rows are moved, so unit and price stay with their reference.
function sortResults() {
    const tbody = document.querySelector('#results-table tbody');
    if (!tbody) return;
    const collator = new Intl.Collator('es', { numeric: true, sensitivity: 'base' });
    const rows = Array.from(tbody.rows);
    rows.sort(function (a, b) {
        return collator.compare(a.cells[0].textContent.trim(), b.cells[0].textContent.trim());
    });
    rows.forEach(function (tr) { tbody.appendChild(tr); });
}

// Copy results to clipboard (plain text, current table order)
function copyResults() {
    const raw = document.getElementById('raw-result');
    if (!raw) return;

    if (document.querySelector('#results-table tbody tr')) {
        raw.value = tableToText();
    }
    const text = raw.value;
    const btn = document.getElementById('btn-copy');
    const icon = document.getElementById('copy-icon');
    const label = document.getElementById('copy-label');

    navigator.clipboard.writeText(text).then(function () {
        // Success feedback
        btn.classList.add('copied');
        icon.textContent = '✅';
        label.textContent = '¡Copiado!';
        setTimeout(function () {
            btn.classList.remove('copied');
            icon.textContent = '📋';
            label.textContent = 'Copiar Resultado';
        }, 2000);
    }).catch(function () {
        // Fallback for older browsers
        raw.classList.remove('hidden');
        raw.select();
        document.execCommand('copy');
        raw.classList.add('hidden');
        icon.textContent = '✅';
        label.textContent = '¡Copiado!';
        setTimeout(function () {
            icon.textContent = '📋';
            label.textContent = 'Copiar Resultado';
        }, 2000);
    });
}

document.addEventListener('DOMContentLoaded', function () {
    const fileInput = document.getElementById('pdf-input');
    const fileLabel = document.querySelector('.file-input-label');
    const fileName = document.querySelector('.file-name');
    const form = document.querySelector('form');
    const submitBtn = document.querySelector('.btn-primary');

    // File input change handler
    if (fileInput) {
        fileInput.addEventListener('change', function (e) {
            if (this.files && this.files.length > 0) {
                const file = this.files[0];
                fileLabel.classList.add('has-file');
                fileName.textContent = file.name;
                fileName.classList.add('show');
            } else {
                fileLabel.classList.remove('has-file');
                fileName.textContent = '';
                fileName.classList.remove('show');
            }
        });
    }

    // Form submit handler - add loading state
    if (form && submitBtn) {
        form.addEventListener('submit', function (e) {
            if (fileInput && fileInput.files.length > 0) {
                submitBtn.disabled = true;
                submitBtn.innerHTML = '<span class="loading"></span> Procesando...';
            }
        });
    }

    // Animate table rows on load
    const tableRows = document.querySelectorAll('tbody tr');
    tableRows.forEach((row, index) => {
        row.style.animation = `fadeIn 0.5s ease-in-out ${index * 0.05}s both`;
    });

    // Add smooth scroll for results
    const resultsSection = document.querySelector('.results-section');
    if (resultsSection) {
        setTimeout(() => {
            resultsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }, 300);
    }
});

// Drag and drop functionality
const container = document.querySelector('.container');
const fileInputWrapper = document.querySelector('.file-input-wrapper');
const fileInput = document.getElementById('pdf-input');

if (container && fileInputWrapper && fileInput) {
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        container.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        container.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        container.addEventListener(eventName, unhighlight, false);
    });

    function highlight(e) {
        fileInputWrapper.querySelector('.file-input-label').style.borderColor = 'var(--primary-color)';
        fileInputWrapper.querySelector('.file-input-label').style.background = '#f8f9ff';
    }

    function unhighlight(e) {
        fileInputWrapper.querySelector('.file-input-label').style.borderColor = '';
        fileInputWrapper.querySelector('.file-input-label').style.background = '';
    }

    container.addEventListener('drop', handleDrop, false);

    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = dt.files;

        if (files.length > 0 && files[0].type === 'application/pdf') {
            fileInput.files = files;
            const event = new Event('change', { bubbles: true });
            fileInput.dispatchEvent(event);
        }
    }
}
