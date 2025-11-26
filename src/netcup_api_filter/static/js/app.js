// Copy to clipboard utility
function copyToClipboard(text, element) {
    navigator.clipboard.writeText(text).then(() => {
        // Visual feedback
        const originalOpacity = element.style.opacity;
        element.style.opacity = '1';
        element.style.transform = 'scale(1.2)';
        
        setTimeout(() => {
            element.style.opacity = originalOpacity;
            element.style.transform = 'scale(1)';
        }, 200);
        
        // Show toast notification (if available)
        if (typeof showToast === 'function') {
            showToast('Copied to clipboard!');
        }
    }).catch(err => {
        console.error('Failed to copy:', err);
        alert('Failed to copy to clipboard');
    });
}

// Initialize real-time table search with List.js
document.addEventListener('DOMContentLoaded', function() {
    // Find all Flask-Admin tables
    const tables = document.querySelectorAll('table.table');
    
    tables.forEach((table, index) => {
        const tableId = `list-table-${index}`;
        table.id = tableId;
        
        // Add wrapper for List.js
        const wrapper = document.createElement('div');
        wrapper.id = `list-wrapper-${index}`;
        wrapper.classList.add('list-wrapper');
        table.parentNode.insertBefore(wrapper, table);
        
        // Add search input
        const searchDiv = document.createElement('div');
        searchDiv.classList.add('list-search-container', 'mb-3');
        searchDiv.innerHTML = `
            <input type="text" 
                   class="search form-control" 
                   placeholder="🔍 Real-time search..." 
                   style="max-width: 400px;">
            <small class="text-muted ms-2">
                <span class="list-count"></span> results
            </small>
        `;
        wrapper.appendChild(searchDiv);
        
        // Move table into wrapper
        wrapper.appendChild(table);
        
        // Get column headers for List.js
        const headers = Array.from(table.querySelectorAll('thead th')).map((th, i) => {
            const text = th.textContent.trim().toLowerCase().replace(/\s+/g, '-');
            return text || `col-${i}`;
        });
        
        // Add list class to tbody rows
        const tbody = table.querySelector('tbody');
        if (tbody) {
            tbody.classList.add('list');
            
            // Add data attributes for searchable columns
            tbody.querySelectorAll('tr').forEach(row => {
                row.querySelectorAll('td').forEach((td, i) => {
                    const colName = headers[i];
                    if (colName) {
                        td.classList.add(colName);
                    }
                });
            });
            
            // Initialize List.js
            try {
                const options = {
                    valueNames: headers.filter(h => h && !h.includes('action') && !h.includes('logs')),
                    page: 50,  // Match page_size from admin_ui.py
                    pagination: {
                        innerWindow: 3,
                        outerWindow: 1,
                    }
                };
                
                const listObj = new List(`list-wrapper-${index}`, options);
                
                // Update count display
                listObj.on('updated', function() {
                    const count = listObj.visibleItems.length;
                    const total = listObj.items.length;
                    const countEl = wrapper.querySelector('.list-count');
                    if (countEl) {
                        countEl.textContent = count === total ? 
                            `${total} total` : 
                            `${count} of ${total}`;
                    }
                });
                
                // Trigger initial count
                listObj.update();
            } catch (e) {
                console.error('List.js initialization failed:', e);
            }
        }
    });
});
