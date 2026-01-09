/* ===================================================================
   THEME & DENSITY MANAGEMENT
   Alpine.js Store with localStorage persistence
   =================================================================== */

// Initialize Alpine.js store before Alpine loads
document.addEventListener('alpine:init', () => {
    Alpine.store('theme', {
        // Available themes and densities
        themes: ['cobalt-2', 'graphite', 'obsidian-noir', 'ember', 'jade', 'gold-dust'],
        densities: ['comfortable', 'compact', 'ultra-compact'],
        
        // Current settings (loaded from localStorage)
        current: localStorage.getItem('naf-theme') || 'cobalt-2',
        density: localStorage.getItem('naf-density') || 'comfortable',
        
        // Initialize theme on page load
        init() {
            this.applyTheme(this.current);
            this.applyDensity(this.density);
        },
        
        // Set and apply theme
        set(themeName) {
            if (this.themes.includes(themeName)) {
                this.current = themeName;
                localStorage.setItem('naf-theme', themeName);
                this.applyTheme(themeName);
            }
        },
        
        // Set and apply density
        setDensity(densityName) {
            if (this.densities.includes(densityName)) {
                this.density = densityName;
                localStorage.setItem('naf-density', densityName);
                this.applyDensity(densityName);
            }
        },
        
        // Apply theme class to body
        applyTheme(themeName) {
            const body = document.body;
            // Remove all theme classes
            this.themes.forEach(t => {
                body.classList.remove(`theme-${t}`);
            });
            // Apply new theme (cobalt-2 is default, no class needed)
            if (themeName !== 'cobalt-2') {
                body.classList.add(`theme-${themeName}`);
            }
        },
        
        // Apply density class to body
        applyDensity(densityName) {
            const body = document.body;
            // Remove all density classes
            this.densities.forEach(d => {
                body.classList.remove(`density-${d}`);
            });
            // Apply new density (comfortable is default, no class needed)
            if (densityName !== 'comfortable') {
                body.classList.add(`density-${densityName}`);
            }
        }
    });
});

// Apply theme/density immediately (before Alpine loads) to prevent flash
(function() {
    const theme = localStorage.getItem('naf-theme') || 'cobalt-2';
    const density = localStorage.getItem('naf-density') || 'comfortable';
    
    // Apply theme class
    if (theme !== 'cobalt-2') {
        document.body.classList.add(`theme-${theme}`);
    }
    
    // Apply density class
    if (density !== 'comfortable') {
        document.body.classList.add(`density-${density}`);
    }
})();

/* ===================================================================
   UTILITY FUNCTIONS
   =================================================================== */

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
    // Find only tables that explicitly request search functionality
    const tables = document.querySelectorAll('table.searchable-table');
    
    // Guard: Skip if List.js library is not loaded
    if (typeof List === 'undefined') {
        if (tables.length > 0) {
            console.warn('List.js not loaded - searchable-table features disabled');
        }
        return;
    }
    
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
