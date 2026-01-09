# Templates Directory Structure

This directory contains Jinja2 templates for the netcup-api-filter web interface.

## Directory Layout

### `/admin`
Admin dashboard pages (authenticated, role-based access):
- Dashboard and statistics
- Account management (CRUD operations)
- Client token management
- Configuration pages (Netcup API, email, system info)
- Audit log viewer
- Theme and password management

### `/account`
User account pages:
- Login/logout flows
- Initial password change
- Account settings

### `/components`
Reusable template fragments included via `{% include %}`:
- Navigation bars
- Form components
- Alert/notification boxes
- Footer elements
- Modal dialogs

### `/errors`
Error page templates:
- 404 Not Found
- 500 Internal Server Error
- Other HTTP error codes

## Base Templates

Two base templates provide consistent layout and functionality:

### `base.html`
Full application layout for authenticated pages:
- Navigation bar with admin menu
- Main content area with flash messages
- Footer with build information
- Theme and density CSS variables
- JavaScript modules for interactive elements
- CSRF token injection

**Used by**: All admin dashboard pages

### `standalone_base.html`
Minimal layout for authentication flows:
- No navigation bar
- Centered content area
- Footer with build info
- Theme support
- CSRF token injection

**Used by**: Login, logout, initial password change

## Template Conventions

- **CSRF Protection**: All forms include `{{ csrf_token() }}` hidden input
- **Flash Messages**: Use `get_flashed_messages(with_categories=true)` for alerts
- **Theme Variables**: CSS custom properties defined in base templates (`--color-bg-primary`, etc.)
- **Responsive Design**: Mobile-first with CSS Grid/Flexbox layouts
- **Accessibility**: Semantic HTML, ARIA labels, keyboard navigation support

### Theming Best Practices

**CRITICAL: Never use hardcoded color classes that break theme consistency.**

#### ❌ AVOID (Theme-Breaking)

```html
<!-- Hardcoded light/dark backgrounds -->
<div class="bg-dark text-light">...</div>
<div class="bg-light text-dark">...</div>

<!-- Hardcoded color assumptions -->
<button class="btn btn-outline-light">...</button>
<span class="badge bg-light text-dark">...</span>

<!-- Inline hardcoded colors -->
<div style="background: #3b82f6;">...</div>
<div style="background: rgba(59, 130, 246, 0.1);">...</div>
```

**Why this breaks:** These assume specific theme backgrounds and won't adapt to user's chosen theme (light/dark/custom).

#### ✅ USE (Theme-Aware)

```html
<!-- Use CSS variables for custom backgrounds -->
<div style="background-color: var(--color-bg-secondary); color: var(--color-text-primary);">...</div>

<!-- Use semantic Bootstrap classes -->
<button class="btn btn-outline-secondary">...</button>
<span class="badge bg-secondary">...</span>
```

#### Available CSS Variables

**Backgrounds:**
- `--color-bg-primary` - Main background
- `--color-bg-secondary` - Card/section backgrounds
- `--color-bg-elevated` - Hover states, active elements, subtle highlights
- `--color-bg-surface` - Modal/overlay backgrounds

**Text:**
- `--color-text-primary` - Main text
- `--color-text-secondary` - Subdued text
- `--color-text-muted` - Placeholder/disabled text

**Borders:**
- `--color-border` - Standard borders
- `--color-border-subtle` - Lighter borders (table rows)
- `--color-border-card` - Card/section borders

**Semantic:**
- `--color-accent` - Primary/link color (adapts per theme)
- `--color-accent-hover` - Hover state
- `--color-accent-rgb` - Accent color as RGB values (for rgba() usage)
- `--color-success`, `--color-warning`, `--color-danger`, `--color-info`

**Active/Focus States:**
For navigation and interactive elements that need to show "active" or "selected" state, use the accent color:
- Text: `color: var(--color-accent)` - Stands out clearly on all themes
- Background: `background: rgba(var(--color-accent-rgb), 0.15)` - Subtle themed highlight
- This pattern works universally because each theme's accent color is designed to contrast with its background

**Note:** Avoid using `--color-bg-elevated` alone for active states - it only makes backgrounds lighter, which doesn't provide clear "selected" indication. Use it for hover states where subtle highlighting is appropriate.

#### Classes That Are SAFE to Use

These classes have **semantic** or **functional** meaning (not color):

- **Font weights**: `fw-light`, `fw-bold`, `fw-semibold` (typography, not color)
- **Icon names**: `bi-lightbulb`, `bi-lightning` (icon identifiers)
- **Navbar variants**: `navbar-dark`, `navbar-light` (Bootstrap semantic variants)
- **Text utilities**: `text-muted` (semantic state)
- **Semantic states**: `bg-warning text-dark`, `bg-danger`, `bg-success` (status indicators)

#### When to Use Semantic Color Pairs

Bootstrap provides semantically meaningful color combinations that **should** be used for status indicators:

```html
<!-- Status indicators - CORRECT usage -->
<span class="badge bg-warning text-dark">Pending</span>
<span class="badge bg-danger">Error</span>
<span class="badge bg-success">Active</span>

<!-- Entropy/security levels - CORRECT usage -->
entropyBadge.className = 'badge bg-warning text-dark';  // Weak
entropyBadge.className = 'badge bg-info text-dark';     // Fair
```

**Rule of thumb**: If the color communicates **meaning** (warning, error, success), use semantic classes. If it's purely **decorative** or for **structure**, use CSS variables or theme-aware classes.

#### Legitimate Hardcoded Colors

**Acceptable use cases:**
1. **Theme swatches** - Theme previews must show actual theme colors
2. **Gradients in theme definitions** - CSS variable values themselves
3. **Landing page hero sections** - Marketing pages with fixed branding

**Example (acceptable):**
```html
<!-- Theme switcher swatch showing actual theme color -->
<span class="theme-swatch" style="background: linear-gradient(135deg, #3b82f6, #0a0e1a)"></span>
```

#### Button Visibility in Alerts

**CRITICAL: Buttons inside matching-color alerts are handled automatically via CSS.**

When using buttons inside alerts, the CSS ensures proper contrast:

```html
<!-- ✅ CORRECT: Buttons are automatically visible -->
<div class="alert alert-warning">
    <p>Pending approvals require review.</p>
    <a href="/review" class="btn btn-warning">Review Now</a>
    <a href="/settings" class="btn btn-outline-warning">Configure</a>
</div>

<div class="alert alert-danger">
    <p>Critical security issue detected.</p>
    <button class="btn btn-danger">Fix Now</button>
</div>
```

**How it works:**
- `.alert-warning .btn-warning` - Automatically gets darker background for contrast
- `.alert-warning .btn-outline-warning` - Automatically gets darker background for contrast
- Same pattern applies for danger, success, info

**You don't need to:**
- ❌ Change button class (`btn-primary` instead of `btn-warning`)
- ❌ Add custom inline styles
- ❌ Use different alert colors

Just use semantically matching colors and CSS handles visibility.

#### Migration Pattern

When updating templates:

1. **Search** for `-light` and `-dark` in class names
2. **Analyze context**: Is this semantic (status) or decorative?
3. **Replace decorative** with CSS variables or `bg-secondary`
4. **Keep semantic** for warnings, errors, success states
5. **Test across themes** - Check Cobalt 2, Dracula, Monokai, Nord, Light modes

### Auto-Refresh Best Practices

**CRITICAL: Never use `location.reload()` for auto-refresh - it destroys UI state.**

#### ❌ AVOID (Disruptive Page Reload)

```javascript
function refreshData() {
    location.reload(); // Closes dropdowns, resets scroll, loses form state
}
setInterval(refreshData, 5000);
```

**Why this breaks:**
- Closes open navigation menus
- Collapses expanded dropdowns (theme selector, config menu)
- Loses scroll position
- Resets form inputs
- Interrupts user interactions

#### ✅ USE (Silent AJAX Refresh)

```javascript
function refreshData() {
    const params = new URLSearchParams(window.location.search);
    
    fetch('/endpoint/data?' + params.toString())
        .then(response => response.text())
        .then(html => {
            // Replace only the data container, preserving UI state
            document.querySelector('#dataContainer').innerHTML = html;
            
            // Re-initialize client-side enhancements if needed
            if (window.dataList) {
                window.dataList.reIndex(); // List.js sorting
            }
        })
        .catch(error => console.error('Refresh failed:', error));
}
setInterval(refreshData, 5000);
```

#### Implementation Pattern

**1. Create AJAX endpoint** (returns HTML fragment, not full page):

```python
@admin_bp.route('/data')
@require_admin
def data_endpoint():
    # Apply same filters as main page
    items = query.filter(...).all()
    
    # Return just the table rows/cards (no layout)
    return render_template('data_table.html', items=items)
```

**2. Extract reusable fragment template**:

```html
{# data_table.html - Just the rows, no <table> wrapper #}
{% for item in items %}
<tr>
    <td>{{ item.name }}</td>
    <td>{{ item.status }}</td>
</tr>
{% endfor %}
```

**3. Update JavaScript** to use AJAX:

```javascript
// Preserve filters/pagination in refresh
const params = new URLSearchParams(window.location.search);
fetch('/endpoint/data?' + params.toString())
```

#### When Page Reload IS Acceptable

**Post-mutation operations** (after user action completes):
- After approving/rejecting accounts (bulk actions)
- After deleting records
- After configuration changes
- After form submissions

These are **intentional full refreshes** after state changes, not continuous auto-refresh.

**Example (acceptable):**
```javascript
function deleteSomething(id) {
    fetch(`/delete/${id}`, { method: 'DELETE' })
        .then(() => location.reload()) // OK: user-initiated action completed
        .catch(error => alert(error));
}
```

## Testing

Templates are validated via:
- **Interactive UI tests**: `ui_tests/tests/test_ui_interactive.py` (JavaScript, CSS, navigation)
- **User journey tests**: `ui_tests/tests/test_user_journeys.py` (end-to-end workflows)
- **Visual regression**: Screenshot comparison in deployment workflow

See `AGENTS.md` for testing guidelines and `docs/UI_TESTING_GUIDE.md` for comprehensive testing documentation.
