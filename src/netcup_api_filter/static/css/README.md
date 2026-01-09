# CSS Styling Guide

This directory contains the styling system for the Netcup API Filter admin interface.

## Files

- **`app.css`** - Custom theme system (dark mode, 17 themes, density control)
- **Bootstrap 5** - Utility-first CSS framework (loaded from CDN)

## Bootstrap 5 Utility Classes

The UI uses Bootstrap 5's utility classes for rapid, consistent styling. This is a utility-first approach where you apply small, single-purpose classes directly to HTML elements.

### Spacing System

Bootstrap uses a standardized spacing scale (0-5) with shorthand notation:

**Format**: `{property}{sides}-{size}`

**Properties:**
- `m` = margin
- `p` = padding

**Sides:**
- `t` = top
- `b` = bottom
- `s` = start (left in LTR)
- `e` = end (right in LTR)
- `x` = horizontal (left + right)
- `y` = vertical (top + bottom)
- *(no letter)* = all sides

**Sizes:**
- `0` = 0 (removes spacing)
- `1` = 0.25rem (4px)
- `2` = 0.5rem (8px)
- `3` = 1rem (16px)
- `4` = 1.5rem (24px)
- `5` = 3rem (48px)
- `auto` = automatic (for margins only)

**Examples:**
```html
<!-- mb-0 = margin-bottom: 0 -->
<p class="mb-0">No bottom margin</p>

<!-- mt-2 = margin-top: 0.5rem (8px) -->
<div class="mt-2">Small top margin</div>

<!-- mb-4 = margin-bottom: 1.5rem (24px) -->
<section class="mb-4">Large bottom margin</section>

<!-- px-3 = padding-left: 1rem, padding-right: 1rem -->
<div class="px-3">Horizontal padding</div>

<!-- py-2 = padding-top: 0.5rem, padding-bottom: 0.5rem -->
<div class="py-2">Vertical padding</div>

<!-- Common combination: mb-0 mt-2 -->
<!-- Removes bottom margin, adds small top margin -->
<p class="mb-0 mt-2">Second line of alert text</p>
```

### Layout & Display

**Flexbox:**
```html
<!-- Create flex container -->
<div class="d-flex">Flex container</div>

<!-- Direction -->
<div class="d-flex flex-row">Row (default)</div>
<div class="d-flex flex-column">Column</div>

<!-- Justify content (horizontal alignment) -->
<div class="d-flex justify-content-start">Left aligned</div>
<div class="d-flex justify-content-center">Centered</div>
<div class="d-flex justify-content-between">Space between</div>
<div class="d-flex justify-content-end">Right aligned</div>

<!-- Align items (vertical alignment) -->
<div class="d-flex align-items-center">Vertically centered</div>
<div class="d-flex align-items-start">Top aligned</div>

<!-- Gap (spacing between flex items) -->
<div class="d-flex gap-2">Flex with 0.5rem gaps</div>
<div class="d-flex gap-3">Flex with 1rem gaps</div>

<!-- Wrap -->
<div class="d-flex flex-wrap">Wrapping flex container</div>

<!-- Grow/shrink -->
<div class="flex-grow-1">Grows to fill space</div>
```

**Display:**
```html
<div class="d-none">Hidden</div>
<div class="d-block">Block display</div>
<div class="d-inline">Inline display</div>
<div class="d-inline-block">Inline-block display</div>
```

### Typography

**Text Alignment:**
```html
<p class="text-center">Centered text</p>
<p class="text-start">Left aligned (LTR)</p>
<p class="text-end">Right aligned (LTR)</p>
```

**Text Colors:**
```html
<p class="text-primary">Primary color</p>
<p class="text-secondary">Secondary color</p>
<p class="text-muted">Muted (gray) text</p>
<p class="text-success">Success (green)</p>
<p class="text-warning">Warning (yellow/orange)</p>
<p class="text-danger">Danger (red)</p>
<p class="text-info">Info (cyan)</p>
<p class="text-white">White text</p>
```

**Font Weight & Style:**
```html
<strong>Bold text</strong>
<em>Italic text</em>
<p class="fw-bold">Bold weight</p>
<p class="fw-normal">Normal weight</p>
<p class="fw-light">Light weight</p>
<p class="fst-italic">Italic style</p>
```

**Font Size:**
```html
<p class="fs-1">Largest (h1 size)</p>
<p class="fs-6">Smallest (h6 size)</p>
<small class="small">Small text (80% of parent)</small>
```

**Text Decoration:**
```html
<a class="text-decoration-none">No underline</a>
<a class="text-decoration-underline">Underlined</a>
```

### Colors & Backgrounds

**Background Colors:**
```html
<div class="bg-primary">Primary background</div>
<div class="bg-secondary">Secondary background</div>
<div class="bg-success">Success background</div>
<div class="bg-danger">Danger background</div>
<div class="bg-warning">Warning background</div>
<div class="bg-info">Info background</div>
<div class="bg-dark">Dark background</div>
<div class="bg-light">Light background</div>
```

**Border:**
```html
<div class="border">Border on all sides</div>
<div class="border-top">Top border only</div>
<div class="border-0">No border</div>
<div class="rounded">Rounded corners</div>
<div class="rounded-circle">Circular</div>
```

### Bootstrap Components

**Alerts:**
```html
<div class="alert alert-info mb-4 text-center">
    <div class="mb-2">
        <i class="bi bi-info-circle-fill me-2"></i>
        <strong>Alert Title</strong>
    </div>
    <div class="small">Alert message content</div>
</div>
```

**Badges:**
```html
<span class="badge bg-success">Success</span>
<span class="badge bg-danger">Error</span>
<span class="badge bg-secondary">Neutral</span>
```

**Buttons:**
```html
<button class="btn btn-primary">Primary Action</button>
<button class="btn btn-secondary">Secondary</button>
<button class="btn btn-outline-primary">Outline</button>
<button class="btn btn-sm">Small button</button>
<button class="btn btn-lg">Large button</button>
```

**Forms:**
```html
<div class="mb-3">
    <label class="form-label" for="email">Email</label>
    <input type="email" class="form-control" id="email">
</div>

<!-- Input groups -->
<div class="input-group">
    <span class="input-group-text"><i class="bi bi-envelope"></i></span>
    <input type="text" class="form-control">
</div>
```

### Common Patterns in This Project

**Alert with Icon + Title + Content (2 lines):**
```html
<div class="alert alert-info mb-4 text-center">
    <div class="mb-2">
        <i class="bi bi-info-circle-fill me-2"></i>
        <strong>Title</strong>
    </div>
    <div class="small">Content text here</div>
</div>
```
- `mb-4` on alert = bottom margin for spacing from next element
- `text-center` = center all content
- `mb-2` on first div = spacing between title and content
- `me-2` on icon = right margin (space between icon and text)
- `small` = smaller font size for content

**Form Field with Label:**
```html
<div class="mb-4">
    <label class="form-label" for="field">Field Name</label>
    <input type="text" class="form-control" id="field">
</div>
```
- `mb-4` = bottom margin between form fields

**Navigation/Action Bar:**
```html
<div class="d-flex justify-content-between align-items-center mb-2">
    <label class="form-label mb-0">Label</label>
    <button class="btn btn-primary btn-xs">Action</button>
</div>
```
- `d-flex` = flex container
- `justify-content-between` = space items to edges
- `align-items-center` = vertically center items
- `mb-0` on label = remove default label margin when in flex container

**Horizontal Layout:**
```html
<div class="d-flex gap-2 flex-wrap">
    <span class="badge bg-success">Item 1</span>
    <span class="badge bg-info">Item 2</span>
    <span class="badge bg-warning">Item 3</span>
</div>
```
- `gap-2` = 0.5rem spacing between items
- `flex-wrap` = items wrap to next line if needed

## Custom Theme System (app.css)

The project includes a custom dark theme system with:

- **17 color themes** (Deep Ocean, Graphite, Cobalt 2, etc.)
- **3 density levels** (Comfortable, Compact, Ultra Compact)
- **CSS custom properties** for theming (`--color-bg-primary`, `--color-text-primary`, etc.)

Custom properties are applied in templates via data attributes:
```html
<body data-theme="cobalt-2" data-density="comfortable">
```

## Resources

- **Bootstrap 5 Documentation**: https://getbootstrap.com/docs/5.3/
- **Bootstrap 5 Utilities**: https://getbootstrap.com/docs/5.3/utilities/spacing/
- **Bootstrap Icons**: https://icons.getbootstrap.com/

## Best Practices

1. **Prefer utilities over custom CSS** - Use Bootstrap classes first
2. **Maintain spacing consistency** - Use the standard scale (0-5)
3. **Mobile-first** - Bootstrap is responsive by default
4. **Semantic HTML** - Use proper tags (`<button>`, `<form>`, etc.)
5. **Accessibility** - Include ARIA labels and keyboard navigation
6. **Theme-aware** - Use CSS custom properties from `app.css` for colors

## Testing

All template styling is validated via:
- `ui_tests/tests/test_ui_interactive.py` - Interactive elements, CSS variables
- `ui_tests/tests/test_user_journeys.py` - End-to-end user workflows
- Visual regression tests with screenshot comparison

Run tests: `./run-local-tests.sh`
