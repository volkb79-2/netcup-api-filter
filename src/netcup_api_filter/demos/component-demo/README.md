# Component Demo (Custom CSS)

**Route:** `/component-demo`

## Purpose

Comprehensive design system reference page showcasing all UI components 
with 100% custom CSS and 17 color themes.

## Features

### Themes (17)
Cobalt 2, Graphite, Obsidian Noir, Ember, Jade, Gold Dust, Rose Quartz,
Midnight, Steel, Mocha, Arctic, Sunset, Forest, Ocean, Neon, Crimson, Amethyst

### Sections (11)
1. **Typography** - Headings, body text, monospace, links
2. **Buttons** - Primary, secondary, outline, sizes (xs-xl), icon buttons
3. **Cards** - Basic, with headers, interactive, statistics cards
4. **Forms** - Inputs, selects, checkboxes, radios, sliders, toggles
5. **Tables** - Basic, striped, hoverable, sortable, with actions
6. **Badges** - Status indicators, counts, colored variants
7. **Alerts** - Success, warning, danger, info, dismissible
8. **Modals** - Standard, confirmation, with forms
9. **Navigation** - Tabs, pills, breadcrumbs
10. **Loading** - Spinners, skeleton loaders, progress bars
11. **Miscellaneous** - Tooltips, popovers, accordions

## Technical Details

- **Zero Dependencies:** No Bootstrap, no external CSS
- **~2000 Lines:** Self-contained HTML with embedded CSS
- **CSS Variables:** Theme switching via `data-theme` attribute
- **Accent Glow:** Each theme defines `--color-accent-glow` for consistent effects

## File Structure

```
component-demo/
└── index.html    # Self-contained demo (~108KB)
```

## Comparison

See [component-demo-bs5](../component-demo-bs5/) for Bootstrap 5 version.
