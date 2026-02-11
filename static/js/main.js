// ===================================
// Modern PDF Extractor - Main Script
// ===================================

// Copy results to clipboard (plain text, exact format)
function copyResults() {
    const raw = document.getElementById('raw-result');
    if (!raw) return;

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
