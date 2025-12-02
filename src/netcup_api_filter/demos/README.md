# Demo Pages

This folder contains design system reference pages for comparing different CSS/theming approaches.

## Demo Overview

| Demo | Route | Purpose |
|------|-------|---------|
| [theme-demo](theme-demo/) | `/theme-demo` | Original custom CSS theme demo with 6 themes |
| [theme-demo2](theme-demo2/) | `/theme-demo2` | Bootstrap 5 migration demo with 17 themes |
| [component-demo](component-demo/) | `/component-demo` | Custom CSS design system (100% custom, zero deps) |
| [component-demo-bs5](component-demo-bs5/) | `/component-demo-bs5` | Bootstrap 5 design system reference |

## Purpose

These demos help evaluate:
1. **Custom CSS vs Bootstrap 5** - Which approach to use for admin/client pages
2. **Theme implementation** - How CSS variables enable theming
3. **Component patterns** - UI patterns like forms, tables, timelines, modals
4. **Visual regression** - Reference for detecting unintended style changes

## Usage

All demos are served as static HTML files via Flask's `send_from_directory()`.
Routes are defined in `app.py`.
