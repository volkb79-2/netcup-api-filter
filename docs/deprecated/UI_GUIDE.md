# Netcup API Filter · UI Guide

> Part of the active documentation set in `/docs`. See `docs/README.md` for context.

This document describes the current UI architecture, development patterns, and deployment workflow for the Netcup API Filter. It supersedes all previous UI docs.

## 1. Architecture Overview

- **Backend**: Flask + Flask-Admin + SQLAlchemy + Jinja2
- **Frontend**: Bootstrap 5, Alpine.js 3.x, List.js 2.3, custom CSS (`static/css/app.css`)
- **Theme**: Dark blue-black palette with soft gradients and glassy cards
- **Templates**: Shared base templates with role-specific layers for admin and client portals

## 2. Stack Details

| Layer | Technology | Notes |
|-------|------------|-------|
| CSS Framework | Bootstrap 5.3 (CDN) | Provides grid, utilities, JS bundle |
| Styling | `static/css/app.css` | Defines variables, layout, utilities, component skins |
| Reactive JS | Alpine.js (defer) | Lightweight reactivity for sorting, toggles, etc. |
| Tables | List.js | Optional client-side filtering/sorting support |
| Server Views | Flask-Admin + custom Flask blueprints | Admin CRUD + client portal |

## 3. Template Structure

```
templates/
├── base_modern.html      # Root shell (Bootstrap, scripts, flash handling)
├── admin_base.html       # Authenticated admin layout (nav, header)
├── client_base.html      # Authenticated client layout (nav, header)
├── admin/
│   ├── master_modern.html   # Flask-Admin master
│   ├── *_modern.html        # Dashboard, config, auth screens
│   └── model/               # CRUD create/edit/list overrides
└── client/
    ├── *_modern.html        # Login, dashboard, domain detail, record form, activity
```

**Adding a new page**:
1. Create a template that extends `admin_base.html` or `client_base.html`.
2. Add a view/route that renders the new template.
3. Use cards, grids, and buttons from `app.css` (no inline styles when possible).

## 4. Design System

### Colors (CSS variables)
```
--color-bg-primary   #0a0e1a   --color-accent      #3b82f6
--color-bg-elevated  #1a2234   --color-success     #10b981
--color-border       rgba(59,130,246,0.2)
--color-text-primary #f3f4f6   --color-text-muted  #6b7280
```
Gradients: `linear-gradient(135deg, #1e3a8a, #0a0e1a)` and `linear-gradient(180deg, rgba(26,34,52,.95), rgba(17,24,39,.95))`.

### Typography & Layout
- Font stack: `-apple-system, BlinkMacSystemFont, Inter, Segoe UI, Roboto`
- Base font size: 16px, line height: 1.6
- Utility classes: `.d-flex`, `.grid`, `.grid-cols-{1-4}`, `.gap-*`, `.mt-*`, `.mb-*`, `.text-muted`, `.text-sm`

### Components
- **Cards**: `.card` + `.card-header` + `.card-body`
- **Buttons**: `.btn`, `.btn-primary`, `.btn-outline`, `.btn-danger`, `.btn-sm`
- **Forms**: `.form-group`, `.form-label`, `.form-control`, `.form-text`
- **Tables**: `.table` within `.table-container`; optional `.sortable` headers + Alpine sort helper
- **Alerts**: `.alert alert-success|danger|warning|info`
- **Badges**: `.badge badge-success|danger|warning|info`

## 5. JavaScript Patterns

### Alpine.js Helpers
```html
<div x-data="{ open: false }">
  <button @click="open = !open">Toggle</button>
  <div x-show="open">Panel</div>
</div>
```

### Table Sorting Example
```html
<table class="table" x-data="tableSort()" x-init="init($refs.tbody)">
  <thead>
    <th class="sortable" @click="sort('hostname')" :class="indicator('hostname')">Hostname</th>
  </thead>
  <tbody x-ref="tbody">...</tbody>
</table>
```
```javascript
function tableSort() {
  return {
    column: 'hostname',
    direction: 'asc',
    init(tbody) { this.tbody = tbody },
    indicator(col) { return { 'asc': this.column===col && this.direction==='asc', 'desc': this.column===col && this.direction==='desc' } },
    sort(col) { this.direction = this.column===col && this.direction==='asc' ? 'desc' : 'asc'; this.column = col; this.apply(); },
    apply() {
      const rows = [...this.tbody.querySelectorAll('tr')];
      const idx = { hostname: 1, type: 2 }[this.column];
      rows.sort((a,b) => a.cells[idx].textContent.localeCompare(b.cells[idx].textContent, undefined, { numeric: true }));
      if (this.direction === 'desc') rows.reverse();
      rows.forEach(row => this.tbody.appendChild(row));
    }
  }
}
```
(List.js can be introduced when list-wide search/filtering is needed.)

## 6. Development Workflow

1. **Local preview**
   - Run Flask (or preferred WSGI entrypoint) locally.
   - Use the Playwright container in `tooling/playwright/` for scripted UI checks.
2. **Styling**
   - Update `static/css/app.css` (respect variables & utilities; keep ASCII comments concise).
   - Prefer utility classes over ad-hoc inline styles.
3. **Templates**
   - Keep markup semantic (nav/section/main/footer).
   - Wrap content inside `.card` or `.table-container` to maintain spacing.
4. **Scripts**
   - Inline Alpine snippets for simple interactions.
   - Add dedicated JS modules only when complexity grows beyond Alpine's scope.

## 7. Testing & Deployment

| Task | Command/Step |
|------|--------------|
| Verify modern UI files exist | `./test_modern_ui.sh` |
| Remove legacy HTML/CSS | `./cleanup_legacy_ui.sh` |
| Build deployment package | `python build_deployment.py` |
| Deploy to hosting | `./build-and-deploy.sh` |
| Visual regression | Use Playwright MCP against `PUBLIC_FQDN` |

Post-deploy smoke test checklist:
- Admin: login, dashboard stats, CRUD views, Netcup/email/system screens, password change.
- Client: token login, dashboard cards, domain detail (sorting & actions), record create/edit/delete, activity log.
- Visual: header/nav, cards, alerts, responsive breakpoints, console free of errors.

## 8. Tooling Notes

- **Playwright**: `cd tooling/playwright && docker compose up -d`, then run tests with `docker exec playwright pytest /workspaces/netcup-api-filter/ui_tests/tests -v`. For MCP access, use SSH tunnel to expose port 8765 internally.
- **Docs to keep handy**: `UI_GUIDE.md` (this file). All earlier UI_* references were removed.
- **Scripts**: `test_modern_ui.sh`, `cleanup_legacy_ui.sh`, `report_ui_modernization.sh` are available for validation/reporting.

## 9. FAQ

**How do I tweak the palette?**  Edit the `:root` variables at the top of `static/css/app.css`.

**Do I need Node/NPM?**  No. All assets are loaded via CDN; just update templates/CSS and redeploy.

**Where do I add a new nav item?**  Update `templates/admin_base.html` or `templates/client_base.html`.

**How do I test a UI change quickly?**  Run the Flask app locally and use the Playwright MCP harness for scripted flows, or hit the endpoints directly in a browser.
