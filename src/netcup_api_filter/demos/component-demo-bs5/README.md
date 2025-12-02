# Component Demo (Bootstrap 5)

**Route:** `/component-demo-bs5`

## Purpose

Design system reference using Bootstrap 5.3 with CSS custom property overrides
for theming. Demonstrates what's achievable with vanilla BS5 vs custom CSS.

## Features

### Themes (7)
Cobalt 2, Graphite, Obsidian Noir, Ember, Jade, Rose Quartz, Gold Dust

### Sections (12)
1. **Typography** - Headings, body text, monospace, links
2. **Buttons** - BS5 variants plus themed accent colors
3. **Cards** - BS5 cards with themed borders and backgrounds
4. **Forms** - BS5 form controls with visible range sliders
5. **Tables** - Client list with action buttons, DNS records table
6. **Badges** - BS5 badges with semantic colors
7. **Alerts** - BS5 alerts with dismiss functionality
8. **Modals** - Themed with 2px borders and glow effects
9. **Navigation** - Tabs, pills with hover/active distinction
10. **Loading** - Progress bars, spinners
11. **Miscellaneous** - Tooltips, popovers, accordions, collapse
12. **Complex Forms** - Password change, activity timeline, audit logs

### Complex Forms Section
- **Change Password:** Button beside label, strength meter, entropy display
- **Activity Timeline:** 3-column layout with status-colored dots
- **Audit Logs Table:** Expandable detail rows with JSON request/response

## Technical Details

- **Bootstrap 5.3:** Dark mode with `data-bs-theme="dark"`
- **CSS Variable Overrides:** Theme switching via body class
- **Vanilla vs Custom:**
  - ✅ Vanilla: Modal/popover borders, nav pills, table styling
  - ⚠️ Custom CSS required: Tooltip theming, glow effects, range track

## File Structure

```
component-demo-bs5/
└── index.html    # BS5 demo (~50KB, CDN links for BS5)
```

## Dependencies

- Bootstrap 5.3.2 (CDN)
- Bootstrap Icons 1.11.1 (CDN)

## Comparison

See [component-demo](../component-demo/) for 100% custom CSS version.
