# Theme Demo

**Route:** `/theme-demo`

## Purpose

Original custom CSS theme demonstration with 6 color themes and 3 UI density modes.

## Features

- **6 Color Themes:** Cobalt 2, Graphite, Obsidian Noir, Ember, Jade, Gold Dust
- **3 Density Modes:** Comfortable, Compact, Ultra Compact
- **Theme Switcher:** Dropdown in sidebar with live preview
- **Component Showcase:** Typography, buttons, forms, tables, cards, badges

## Technical Details

- **100% Custom CSS:** No external dependencies
- **CSS Variables:** All theming via `--color-*` custom properties
- **localStorage Persistence:** Theme and density preferences saved
- **Flash Prevention:** Inline script applies theme before render

## File Structure

```
theme-demo/
└── index.html    # Self-contained demo with embedded CSS
```

## Usage

This demo serves as a reference for the custom CSS theming approach used 
in the admin and account portal pages.
