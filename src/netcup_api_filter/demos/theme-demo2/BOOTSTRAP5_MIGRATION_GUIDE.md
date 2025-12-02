# Theme Migration Guide: Demo2 → Bootstrap 5 Admin UI

## Executive Summary

**What we're doing:** Migrating the visual design from `theme-demo2` (100% custom CSS) to the admin UI (Bootstrap 5 + custom overrides).

**The Challenge:** Demo2 uses completely custom CSS classes (`.card-custom`, `.btn-primary-custom`, `.table-custom`), while admin UI uses Bootstrap 5 classes (`.card`, `.btn-primary`, `.table`). Bootstrap 5 has its own internal CSS that must be overridden to achieve visual parity.

**The Strategy:** Create a "Bootstrap 5 Theme Adapter Layer" in `app.css` that maps our CSS custom properties to Bootstrap's internal variables AND overrides Bootstrap's default component styling.

---

## Architecture Comparison

### Demo2 (Custom CSS Framework)
```
┌─────────────────────────────────────────────────────────────┐
│ Theme Variables (CSS Custom Properties)                      │
│ --color-bg-secondary, --color-accent, --gradient-accent     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Custom Component Classes                                     │
│ .card-custom { background: var(--color-bg-secondary); }     │
│ .btn-primary-custom { background: var(--gradient-accent); } │
│ .table-custom { ... }                                        │
└─────────────────────────────────────────────────────────────┘
```

### Admin UI (Bootstrap 5 + Overrides)
```
┌─────────────────────────────────────────────────────────────┐
│ Theme Variables (CSS Custom Properties)                      │
│ --color-bg-secondary, --color-accent, --gradient-accent     │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Bootstrap 5 CDN (External CSS)                               │
│ .card { background-color: var(--bs-card-bg); }              │
│ .btn-primary { background-color: var(--bs-btn-bg); }        │
│ .table { color: var(--bs-table-color); }                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ app.css Theme Adapter Layer (OUR CODE)                       │
│ .card { background: var(--color-bg-secondary) !important; } │
│ .btn-primary { background: var(--gradient-accent); }        │
│ Must override Bootstrap defaults with our theme variables    │
└─────────────────────────────────────────────────────────────┘
```

---

## CSS Custom Properties Mapping

### Required Variables (All themes MUST define these)

| Variable | Purpose | Example (Gold Dust) |
|----------|---------|---------------------|
| `--color-bg-primary` | Body background | `#0a0907` |
| `--color-bg-primary-solid` | Solid body bg (no gradient) | `#0a0907` |
| `--color-bg-secondary` | Card/panel backgrounds | `#13110d` |
| `--color-bg-elevated` | Elevated elements (modals, dropdowns) | `#1b1814` |
| `--color-bg-surface` | Semi-transparent overlays | `rgba(27, 24, 20, 0.8)` |
| `--color-accent` | Primary action color | `#fbbf24` |
| `--color-accent-hover` | Hover state | `#f59e0b` |
| `--color-accent-rgb` | RGB triplet for rgba() | `251, 191, 36` |
| `--color-accent-glow` | Glow/shadow color | `rgba(251, 191, 36, 0.45)` |
| `--gradient-accent` | Button/accent gradient | `linear-gradient(135deg, #fbbf24 0%, #f59e0b 60%, #d97706 100%)` |
| `--gradient-primary` | Body background gradient | `linear-gradient(180deg, #090806 0%, #0c0a07 100%)` |
| `--gradient-bg` | Subtle ambient overlay | `linear-gradient(145deg, rgba(...) 0%, transparent 50%)` |
| `--color-border` | Standard border | `rgba(251, 191, 36, 0.16)` |
| `--color-border-card` | Card borders (brighter) | `rgba(251, 191, 36, 0.30)` |
| `--card-shadow` | Card box-shadow | `0 4px 28px rgba(...)` |
| `--glossy-overlay` | Top highlight on cards | `linear-gradient(180deg, rgba(255,255,255,0.05) 0%, transparent 35%)` |
| `--color-text-primary` | Main text | `#f8fafc` |
| `--color-text-secondary` | Secondary text | `#c8d4e6` |
| `--color-text-muted` | Muted/hint text | `#8fa3c0` |

### Admin-Specific Additions (not in demo2)

These variables are needed for Bootstrap 5 compatibility:

| Variable | Purpose | Notes |
|----------|---------|-------|
| `--color-accent-rgb` | For `rgba(var(--color-accent-rgb), 0.2)` | Bootstrap uses RGB triplets |
| `--color-bg-surface` | Modal/dropdown overlays | Demo2 uses inline rgba |

---

## Component Migration Reference

### 1. Cards

#### Demo2 (Custom)
```css
.card-custom {
    background: var(--color-bg-secondary);
    border: 1px solid var(--color-border-card, var(--color-border));
    border-radius: var(--border-radius-lg);
    box-shadow: var(--card-shadow, 0 4px 16px rgba(0, 0, 0, 0.2));
    position: relative;
}

.card-custom::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: var(--glossy-overlay, transparent);
    pointer-events: none;
    border-radius: var(--border-radius-lg);
}
```

#### Bootstrap 5 Override (app.css)
```css
.card {
    background: var(--color-bg-secondary);
    border: 1px solid var(--color-border-card, var(--color-border));
    border-radius: var(--radius-lg);
    box-shadow: var(--card-shadow, var(--shadow-lg));
    overflow: hidden;
    position: relative;
    transition: transform var(--transition-base), box-shadow var(--transition-base);
}

/* Glossy overlay effect like demo2 */
.card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: var(--glossy-overlay, transparent);
    pointer-events: none;
    border-radius: var(--radius-lg);
}
```

**Status:** ✅ IMPLEMENTED

---

### 2. Buttons (Primary)

#### Demo2 (Custom)
```css
.btn-primary-custom {
    background: var(--gradient-accent);
    color: white;
    border: none;
    box-shadow: 0 2px 6px var(--color-accent-glow, rgba(59, 130, 246, 0.25));
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

.btn-primary-custom:hover {
    filter: brightness(1.08);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px var(--color-accent-glow, rgba(59, 130, 246, 0.35));
}
```

#### Bootstrap 5 Override (app.css)
```css
.btn-primary {
    background: var(--gradient-accent);
    color: white;
    border: none;
    box-shadow: 0 4px 6px -1px rgba(var(--color-accent-rgb), 0.3);
}

.btn-primary:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 6px 8px -1px rgba(var(--color-accent-rgb), 0.4);
    /* Note: Bootstrap 5 uses --bs-btn-hover-bg, we override completely */
}
```

**Status:** ✅ IMPLEMENTED (gradient background)

**TODO:** Add `filter: brightness(1.08)` on hover, verify `text-shadow`.

---

### 3. Buttons (Secondary)

#### Demo2 (Custom)
```css
.btn-secondary-custom {
    background: var(--color-bg-elevated);
    color: var(--color-text-primary);
    border: 1px solid var(--color-border);
}

.btn-secondary-custom:hover {
    background: var(--color-bg-surface);
    border-color: var(--color-accent);
}
```

#### Bootstrap 5 Override (app.css)
```css
.btn-secondary {
    background: var(--color-bg-elevated);
    color: var(--color-text-primary);
    border: 1px solid var(--color-border);
}

.btn-secondary:hover:not(:disabled) {
    background: var(--color-bg-surface);
    border-color: var(--color-accent);
}
```

**Status:** ✅ IMPLEMENTED

---

### 4. Tables

#### Demo2 (Custom)
```css
.table-custom {
    width: 100%;
    border-collapse: collapse;
}

.table-custom th {
    background: var(--color-bg-elevated);
    color: var(--color-text-secondary);
    font-size: var(--font-size-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border-bottom: 2px solid var(--color-border-card, var(--color-border));
}

.table-custom td {
    border-bottom: 1px solid var(--color-border);
    color: var(--color-text-primary);
}

.table-custom tbody tr:hover {
    background: var(--color-bg-elevated);
}
```

#### Bootstrap 5 Override (app.css)
```css
.table {
    width: 100%;
    border-collapse: collapse;
    --bs-table-bg: transparent;
    --bs-table-color: var(--color-text-secondary);
    --bs-table-hover-bg: rgba(59, 130, 246, 0.05);
    --bs-table-hover-color: var(--color-text-primary);
    background: transparent;
}

.table thead {
    background: rgba(59, 130, 246, 0.1);
}

.table th {
    font-weight: 600;
    color: var(--color-text-primary);
    border-bottom: 1px solid var(--color-border);
}

.table td {
    border-bottom: 1px solid var(--color-border-subtle);
    color: var(--color-text-secondary);
}

.table tbody tr:hover {
    background: rgba(59, 130, 246, 0.05);
}
```

**Status:** ⚠️ PARTIAL - Basic colors work, but:

**TODO:**
- Add uppercase/letter-spacing to headers
- Use `--color-bg-elevated` for header background (theme-aware)
- Change hover to use `var(--color-bg-elevated)` instead of hardcoded blue

---

### 5. Badges

#### Demo2 (Custom)
```css
.badge-custom {
    display: inline-flex;
    align-items: center;
    padding: 0.25rem 0.625rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 500;
}

.badge-success {
    background: rgba(16, 185, 129, 0.15);
    color: var(--color-success);
}
```

#### Bootstrap 5 Override (app.css)
```css
.badge {
    display: inline-flex;
    align-items: center;
    padding: 0.25rem 0.75rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.badge-success {
    background: rgba(16, 185, 129, 0.2);
    color: var(--color-success);
}
```

**Status:** ✅ IMPLEMENTED

---

### 6. Form Controls

#### Demo2 (Custom)
```css
.form-input {
    width: 100%;
    background: var(--color-bg-primary);
    border: 1px solid var(--color-border);
    color: var(--color-text-primary);
    border-radius: var(--border-radius-sm);
}

.form-input:focus {
    outline: none;
    border-color: var(--color-accent);
    box-shadow: 0 0 0 3px var(--color-accent-glow, rgba(59, 130, 246, 0.15));
}
```

#### Bootstrap 5 Override (app.css)
```css
.form-control,
.form-select {
    background-color: var(--color-bg-secondary);
    border-color: var(--color-border);
    color: var(--color-text-primary);
}

.form-control:focus,
.form-select:focus {
    background-color: var(--color-bg-secondary);
    border-color: var(--color-accent);
    box-shadow: 0 0 0 3px rgba(var(--color-accent-rgb), 0.2);
    color: var(--color-text-primary);
}
```

**Status:** ✅ IMPLEMENTED

**Note:** Demo2 uses `var(--color-bg-primary)` for inputs, admin uses `var(--color-bg-secondary)`. Consider aligning if needed.

---

### 7. Navbar / Header

#### Demo2 (Custom)
```css
.navbar-custom {
    background: var(--color-bg-secondary);
    border-bottom: 1px solid var(--color-border-card, var(--color-border));
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.25);
}

.navbar-custom::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: var(--glossy-overlay, transparent);
    pointer-events: none;
}
```

#### Bootstrap 5 Override (app.css)
```css
.app-header {
    background: var(--color-bg-secondary);
    border-bottom: 1px solid var(--color-border-card, var(--color-border));
    backdrop-filter: blur(10px);
    position: sticky;
    top: 0;
    z-index: 100;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.25);
}
```

**Status:** ✅ IMPLEMENTED

**TODO:** Add `::after` glossy overlay pseudo-element.

---

### 8. Dropdown Menus

#### Demo2 (Custom)
```css
.dropdown-menu {
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-card, var(--color-border));
    border-radius: var(--border-radius-md);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.dropdown-item:hover {
    background: rgba(255, 255, 255, 0.05);
    color: var(--color-text-primary);
}
```

#### Bootstrap 5 Override (app.css)
```css
.dropdown-menu {
    background: var(--color-bg-secondary);
    border: 1px solid var(--color-border-card);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-xl), 0 0 30px rgba(0, 0, 0, 0.4);
}

.dropdown-item:hover,
.dropdown-item:focus {
    background: var(--color-bg-elevated);
    color: var(--color-text-primary);
}
```

**Status:** ✅ IMPLEMENTED

---

### 9. Alerts

#### Demo2 (Custom)
```css
.alert {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 1rem 1.25rem;
    border-radius: var(--border-radius-md);
    border: 1px solid;
}

.alert-success {
    background: rgba(16, 185, 129, 0.1);
    border-color: rgba(16, 185, 129, 0.3);
    color: #34d399;
}
```

#### Bootstrap 5 Override (app.css)
```css
.alert {
    padding: var(--space-md) var(--space-lg);
    border-radius: var(--radius-md);
    display: flex;
    align-items: flex-start;
    gap: var(--space-md);
}

.alert-success {
    background: rgba(16, 185, 129, 0.15);
    border: 1px solid rgba(16, 185, 129, 0.3);
    color: var(--color-success);
}
```

**Status:** ✅ IMPLEMENTED

---

### 10. Modals

#### Demo2 (Custom)
```css
.modal-overlay {
    background: rgba(0, 0, 0, 0.7);
    backdrop-filter: blur(4px);
}

.modal {
    background: var(--color-bg-secondary);
    border: 1px solid var(--color-border-card, var(--color-border));
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5), 0 0 40px var(--color-accent-glow);
}

.modal::before {
    /* Glossy overlay */
    background: var(--glossy-overlay, transparent);
}
```

#### Bootstrap 5 Override (app.css)
**Status:** ⚠️ NOT IMPLEMENTED

**TODO:** Add Bootstrap 5 modal overrides:
```css
.modal-content {
    background: var(--color-bg-secondary);
    border: 1px solid var(--color-border-card);
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.modal-header {
    border-bottom-color: var(--color-border);
}

.modal-footer {
    border-top-color: var(--color-border);
    background: rgba(0, 0, 0, 0.1);
}

.modal-backdrop {
    background-color: rgba(0, 0, 0, 0.7);
    backdrop-filter: blur(4px);
}
```

---

## Class Name Mapping Reference

| Demo2 Class | Bootstrap 5 Class | Notes |
|-------------|-------------------|-------|
| `.card-custom` | `.card` | Override in app.css |
| `.card-header-custom` | `.card-header` | Override in app.css |
| `.card-body-custom` | `.card-body` | Override in app.css |
| `.btn-primary-custom` | `.btn-primary` | Override in app.css |
| `.btn-secondary-custom` | `.btn-secondary` | Override in app.css |
| `.btn-danger-custom` | `.btn-danger` | Override in app.css |
| `.table-custom` | `.table` | Override in app.css |
| `.form-input` | `.form-control` | Override in app.css |
| `.form-select` (demo2) | `.form-select` | Same class name |
| `.form-textarea` | `.form-control` (textarea) | Override in app.css |
| `.badge-custom` | `.badge` | Override in app.css |
| `.navbar-custom` | `.app-header` | Custom class, not BS5 |
| `.page-title` | `h1` | Use standard headings |
| `.mono` | `.font-monospace` or `.mono` | Either works |

---

## Missing CSS Variables in :root

These variables are used in demo2 but may need explicit defaults in app.css `:root`:

```css
:root {
    /* Border radius - demo2 uses different names */
    --border-radius-sm: 0.375rem;
    --border-radius-md: 0.5rem;
    --border-radius-lg: 0.75rem;
    
    /* We have these as: */
    --radius-sm: 0.375rem;
    --radius-md: 0.5rem;
    --radius-lg: 0.75rem;
}
```

**Action:** Standardize on one naming convention (recommend keeping `--radius-*`).

---

## Density System Comparison

### Demo2 Approach
```css
body.compact {
    --spacing-xs: 0.125rem;
    --spacing-sm: 0.25rem;
    --table-padding: 0.5rem;
    --card-padding: 0.75rem;
    --navbar-height: 44px;
}
```

### Admin Approach  
```css
body.density-compact,
html.density-compact {
    --density-space-xs: 0.25rem;
    --density-space-sm: 0.375rem;
    --density-table-padding: 0.625rem;
    --density-card-padding: 0.875rem;
    --density-navbar-height: 44px;
}
```

**Status:** ✅ IMPLEMENTED (uses `density-*` prefix for clarity)

---

## Migration Checklist

### Phase 1: Core Layout (COMPLETED ✅)
- [x] Body background uses theme gradient
- [x] Card backgrounds use `--color-bg-secondary`
- [x] Card borders use `--color-border-card`
- [x] Card box-shadow uses `--card-shadow`
- [x] Glossy overlay on cards (`::before` pseudo-element)
- [x] Header/navbar uses theme background

### Phase 2: Buttons (MOSTLY COMPLETE)
- [x] Primary button uses `--gradient-accent`
- [x] Primary button hover has lift effect
- [x] Secondary button uses `--color-bg-elevated`
- [ ] Add `filter: brightness(1.08)` on primary hover
- [ ] Add `text-shadow` to primary buttons

### Phase 3: Forms (COMPLETE ✅)
- [x] Input backgrounds use theme colors
- [x] Focus rings use `--color-accent-glow`
- [x] Select dropdowns styled
- [x] Checkboxes use accent color

### Phase 4: Tables (NEEDS WORK)
- [x] Basic table colors work
- [ ] Header background should use `--color-bg-elevated`
- [ ] Add uppercase headers with letter-spacing
- [ ] Hover should use `--color-bg-elevated`

### Phase 5: Additional Components
- [x] Badges
- [x] Alerts
- [x] Dropdowns
- [ ] Modals (Bootstrap 5 specific overrides needed)
- [ ] Pagination (may need theme colors)
- [ ] Tooltips (if used)

### Phase 6: Polish
- [ ] Verify all 17 themes work correctly
- [ ] Test density modes
- [ ] Check mobile responsiveness
- [ ] Validate accessibility (contrast ratios)

---

## Testing Procedure

1. **Deploy locally:**
   ```bash
   ./deploy.sh local --skip-tests
   ```

2. **Start Playwright:**
   ```bash
   cd tooling/playwright && docker compose up -d
   ```

3. **For each theme, verify:**
   - Card background matches `--color-bg-secondary`
   - Button gradients use theme accent color
   - Text is readable (contrast)
   - Borders are visible but subtle

4. **Automated verification (example):**
   ```javascript
   // In Playwright MCP
   const card = document.querySelector('.card');
   const bg = getComputedStyle(card).backgroundColor;
   const expected = getComputedStyle(document.documentElement)
       .getPropertyValue('--color-bg-secondary').trim();
   console.log({ actual: bg, expected });
   ```

---

## Known Issues & Workarounds

### Issue 1: Bootstrap 5 uses `--bs-*` Variables
Bootstrap 5 internally uses variables like `--bs-btn-bg`, `--bs-card-bg`. Our theme variables are ignored unless we explicitly override.

**Workaround:** In app.css, explicitly set Bootstrap variables:
```css
.btn-primary {
    --bs-btn-bg: var(--color-accent);
    --bs-btn-hover-bg: var(--color-accent-hover);
    --bs-btn-border-color: var(--color-accent);
}
```

### Issue 2: CSS Specificity
Bootstrap CDN loads first, our app.css loads after. Sometimes Bootstrap's `!important` or high-specificity selectors win.

**Workaround:** Use `!important` sparingly, or increase specificity:
```css
body .card,
html .card {
    background: var(--color-bg-secondary);
}
```

### Issue 3: Theme on `<html>` vs `<body>`
Themes are applied to both `<html>` and `<body>` for maximum compatibility:
```css
body.theme-gold-dust,
html.theme-gold-dust {
    --color-bg-secondary: #13110d;
    /* ... */
}
```

---

## File Reference

| File | Purpose |
|------|---------|
| `theme-demo2/Theme Demo - Netcup API Filter.html` | Reference implementation (custom CSS) |
| `static/css/app.css` | Bootstrap 5 theme adapter layer |
| `templates/admin/base.html` | HTML structure using Bootstrap 5 classes |
| `BOOTSTRAP5_MIGRATION_GUIDE.md` | This document |

---

## Conclusion

Migrating from demo2's custom CSS to Bootstrap 5 requires a systematic override approach. The key insight is that **we cannot simply copy CSS classes** - we must understand Bootstrap 5's internal variable system and override it with our theme variables.

Progress so far: ~70% complete. Core layout and cards work perfectly. Remaining work focuses on tables, modals, and polish.
