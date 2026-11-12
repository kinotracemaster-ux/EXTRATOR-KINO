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
        }).filter(function (text, i) {
            return !tr.cells[i].classList.contains('col-hidden');
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

// ---- Optional discount column (PRECIO -N%), hidden by default ----
// Reads a price as written in the PDF ('$72,000.00', '$1.000,50', '3.200').
function parsePrice(text) {
    const m = (text || '').trim().match(/^(\$?\s*)(\d[\d.,]*)$/);
    if (!m) return null;
    const pref = m[1], num = m[2];
    const dm = num.match(/([.,])(\d{1,2})$/);
    const decSep = dm ? dm[1] : null;
    const decs = dm ? dm[2].length : 0;
    const thouSep = decSep === '.' ? ',' : decSep === ',' ? '.' :
        (num.indexOf(',') >= 0 ? ',' : num.indexOf('.') >= 0 ? '.' : '');
    const intPart = (dm ? num.slice(0, dm.index) : num).split(thouSep || '\u0000').join('');
    if (!/^\d+$/.test(intPart)) return null;
    const cents = Number(intPart) * 100 + (dm ? Number(dm[2].padEnd(2, '0')) : 0);
    return { cents: cents, pref: pref, decSep: decSep || (thouSep === '.' ? ',' : '.'), thouSep: thouSep, decs: decs };
}

// Writes a value (in cents) with the same format as the PDF price.
function formatPrice(cents, f) {
    const scale = Math.pow(10, 2 - f.decs);
    const units = Math.round(cents / scale);            // value in the last shown digit
    const div = Math.pow(10, f.decs);
    const intStr = String(Math.floor(units / div)).replace(/\B(?=(\d{3})+(?!\d))/g, f.thouSep);
    const decStr = f.decs ? f.decSep + String(units % div).padStart(f.decs, '0') : '';
    return f.pref + intStr + decStr;
}

// Adds, updates or removes the discount column right after PRECIO.
function updateMarkup() {
    const table = document.getElementById('results-table');
    const toggle = document.getElementById('markup-toggle');
    const pctInput = document.getElementById('markup-pct');
    if (!table || !toggle || !pctInput) return;

    const headRow = table.tHead.rows[0];
    const priceIdx = Array.from(headRow.cells).findIndex(function (th) {
        return th.textContent.trim().toUpperCase() === 'PRECIO';
    });
    if (priceIdx < 0) return;
    const markupIdx = priceIdx + 1;
    const exists = headRow.cells[markupIdx] && headRow.cells[markupIdx].classList.contains('markup-col');

    if (!toggle.checked) {
        if (exists) {
            headRow.deleteCell(markupIdx);
            Array.from(table.tBodies[0].rows).forEach(function (tr) { tr.deleteCell(markupIdx); });
        }
        return;
    }

    const pct = parseFloat(String(pctInput.value).replace(',', '.'));
    const valid = isFinite(pct) && pct >= 0 && pct <= 100;
    if (!exists) {
        const th = document.createElement('th');
        th.className = 'markup-col';
        headRow.insertBefore(th, headRow.cells[markupIdx] || null);
    }
    headRow.cells[markupIdx].textContent = valid ? 'PRECIO -' + pct + '%' : 'PRECIO -%';

    Array.from(table.tBodies[0].rows).forEach(function (tr) {
        let td = tr.cells[markupIdx];
        if (!exists) {
            td = tr.insertCell(markupIdx);
            td.className = 'markup-col';
        }
        const p = parsePrice(tr.cells[priceIdx].textContent);
        td.textContent = (p && valid) ? formatPrice(p.cents * (100 - pct) / 100, p) : '';
    });
}

// ---- Optional PRECIO column, hidden by default ----
// The cells stay in the table (the discount column reads them); they are only
// hidden, and hidden cells are left out of the copy.
function updatePriceVisibility() {
    const table = document.getElementById('results-table');
    const toggle = document.getElementById('price-toggle');
    if (!table || !toggle) return;
    const priceIdx = Array.from(table.tHead.rows[0].cells).findIndex(function (th) {
        return th.textContent.trim().toUpperCase() === 'PRECIO';
    });
    if (priceIdx < 0) return;
    Array.from(table.rows).forEach(function (tr) {
        tr.cells[priceIdx].classList.toggle('col-hidden', !toggle.checked);
    });
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
    updatePriceVisibility();
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
