# Theme Demo v2 (Bootstrap 5 Migration)

**Route:** `/theme-demo2`

## Purpose

Bootstrap 5 migration prototype with 17 themes. Used to evaluate migrating
from custom CSS to Bootstrap 5 for the admin/client portal.

## Features

### Themes (17)
Full theme palette matching component-demo: Cobalt 2, Graphite, Obsidian Noir,
Ember, Jade, Gold Dust, Rose Quartz, Midnight, Steel, Mocha, Arctic, Sunset,
Forest, Ocean, Neon, Crimson, Amethyst

### Demo Content
- Theme switcher sidebar
- Typography samples
- Form elements
- Buttons and badges
- Cards and tables

## Technical Details

- **Bootstrap 5.3:** Uses local `bootstrap.min.css`
- **CSS Variable Overrides:** Theme classes override BS5 variables
- **Migration Guide:** See `BOOTSTRAP5_MIGRATION_GUIDE.md`

## File Structure

```
theme-demo2/
├── Theme Demo - Netcup API Filter.html    # Main demo page
├── bootstrap.min.css                       # Local BS5 CSS
└── BOOTSTRAP5_MIGRATION_GUIDE.md          # Migration documentation
```

## Note

This demo was created during the Bootstrap 5 evaluation phase. The final
decision on BS5 vs custom CSS is documented in the component demos.
