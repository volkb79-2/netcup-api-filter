# Deep Dive Review: Admin UI & User Experience

## Context

The admin UI is a critical component providing:
- **Admin Portal**: Account/realm/token management, system config, audit logs
- **Account Portal**: Self-service for account holders (profile, tokens, 2FA)
- **Dashboard**: System statistics, activity overview, quick actions
- **Settings Pages**: Email, GeoIP, rate limits, security settings
- **Responsive Design**: Mobile-friendly, dark/light themes, adjustable density
- **Interactive Elements**: Forms, modals, bulk operations, live validation

## Review Objective

Verify that the UI is:
1. **Complete** - All features implemented and functional
2. **Consistent** - Unified design language, navigation, interactions
3. **Accessible** - WCAG 2.1 compliant, keyboard navigation
4. **Performant** - Fast load times, efficient rendering
5. **User-friendly** - Intuitive workflows, clear feedback

## Review Checklist

### 1. Page Inventory & Completeness

**Files:** `src/netcup_api_filter/templates/admin/*.html`

#### Admin Portal Pages
- [ ] **Login** (`admin/login.html`): Login form with 2FA support
- [ ] **Dashboard** (`admin/dashboard.html`): Overview with stats cards
- [ ] **Accounts** (`admin/accounts.html`): Account management table
- [ ] **Account Create** (`admin/account_create.html`): New account form
- [ ] **Account Edit** (`admin/account_edit.html`): Edit account details
- [ ] **Account Detail** (`admin/account_detail.html`): Single account view
- [ ] **Realms** (`admin/realms.html`): Realm management table
- [ ] **Realm Create** (`admin/realm_create.html`): New realm form with templates
- [ ] **Realm Detail** (`admin/realm_detail.html`): Single realm view
- [ ] **Tokens** (`admin/tokens.html`): Token management table
- [ ] **Settings** (`admin/settings.html`): System configuration
- [ ] **Audit Log** (`admin/audit_logs.html`): Activity log with filtering

#### Account Portal Pages
- [ ] **Login** (`account/login.html`): Account login
- [ ] **Registration** (`account/register.html`): Self-registration
- [ ] **Dashboard** (`account/dashboard.html`): Personal overview
- [ ] **Realm Detail** (`account/realm_detail.html`): Realm management
- [ ] **Token Create** (`account/token_create.html`): Generate new token
- [ ] **Profile** (`account/profile.html`): Account settings
- [ ] **2FA Setup** (`account/2fa_setup.html`): TOTP enrollment

#### Shared/Utility Pages
- [ ] **Error Pages** (`errors/404.html`, `errors/500.html`): Styled error pages
- [ ] **Base Template** (`base.html`): Common layout structure

**Test:**
```bash
# Verify all templates exist
find src/netcup_api_filter/templates -name "*.html" | wc -l
# Should be 20+ templates

# Verify no broken template references
rg "{% extends ['\"]([^'\"]+)['\"] %}" src/netcup_api_filter/templates/ -oNr '$1' | \
  while read tmpl; do
    [ -f "src/netcup_api_filter/templates/$tmpl" ] || echo "Missing: $tmpl"
  done
```

### 2. Navigation Consistency

**Navigation requirements across ALL pages**

#### Navbar (Admin Portal)
- [ ] **Present on all admin pages**: Every admin page has navbar
- [ ] **Same structure**: Consistent links across all pages
- [ ] **Logo/brand**: App name/logo visible
- [ ] **Navigation links**:
  - [ ] Dashboard
  - [ ] Accounts
  - [ ] Realms
  - [ ] Tokens
  - [ ] Audit Log
  - [ ] Settings
- [ ] **User menu**: Dropdown with profile, password change, logout
- [ ] **Mobile responsive**: Collapses to hamburger menu

#### Account Portal Navigation
- [ ] **Account navbar**: Separate navbar for account portal
- [ ] **Consistent structure**: Same pattern as admin navbar
- [ ] **Navigation links**:
  - [ ] Dashboard
  - [ ] My Realms
  - [ ] Profile
  - [ ] Security (2FA)
- [ ] **Logout**: Always accessible

#### Breadcrumbs (Removed per UX update)
- [ ] **No breadcrumbs**: Verify breadcrumbs removed from all pages
- [ ] **Navigation via navbar**: Only navigation method

**Test:**
```bash
# Verify navbar present on all admin pages
rg '<nav class="navbar' src/netcup_api_filter/templates/admin/ | wc -l
# Should match number of admin pages (10+)

# Verify no breadcrumbs remain
rg 'breadcrumb|nav aria-label="breadcrumb"' src/netcup_api_filter/templates/
# Should return no results
```

### 3. Design System & Consistency

**Files:** `src/netcup_api_filter/static/css/`, templates

#### CSS Variables (Theme System)
- [ ] **Theme variables defined**: `--color-bg-primary`, `--color-text-primary`, etc.
- [ ] **Dark mode support**: CSS variables redefined in `[data-bs-theme="dark"]`
- [ ] **Consistent usage**: All colors use CSS variables (not hardcoded hex)
- [ ] **Theme toggle**: Switch between light/dark themes
- [ ] **Theme persistence**: Selected theme saved in localStorage

#### Typography
- [ ] **Font family**: Consistent font stack
- [ ] **Font sizes**: Standardized sizes (h1-h6, body, small)
- [ ] **Font weights**: Consistent weight usage
- [ ] **Line height**: Readable line spacing
- [ ] **No inline styles**: Typography via classes, not style attributes

#### Spacing
- [ ] **Bootstrap spacing**: Uses Bootstrap utility classes (mt-3, p-4, etc.)
- [ ] **Consistent margins**: Same spacing patterns across pages
- [ ] **Density modes**: Compact/comfortable/spacious density options
- [ ] **Whitespace**: Adequate whitespace for readability

#### Colors
- [ ] **Primary color**: Consistent primary blue
- [ ] **Semantic colors**: Success (green), warning (yellow), danger (red), info (blue)
- [ ] **Text colors**: High contrast for readability
- [ ] **Link colors**: Visible, understandable as links
- [ ] **Background colors**: Tables/cards respect theme (not white on dark theme)

**Test:**
```bash
# Check for hardcoded colors (should use CSS variables)
rg 'color:\s*#[0-9a-f]{3,6}' src/netcup_api_filter/templates/
# Should return minimal results (only in CSS, not templates)

# Verify CSS variables usage
rg 'var\(--color-' src/netcup_api_filter/static/css/
# Should show widespread usage
```

### 4. Interactive Elements

**JavaScript-driven features**

#### Password Field Enhancements
- [ ] **Password toggle**: Eye icon toggles visibility
- [ ] **Entropy meter**: Real-time password strength calculation
- [ ] **Generate button**: Creates strong passwords
- [ ] **Password mismatch warning**: Highlights mismatched passwords
- [ ] **Copy to clipboard**: One-click copy for generated passwords

#### Form Validation
- [ ] **Client-side validation**: HTML5 validation attributes
- [ ] **Custom validation**: JavaScript validation for complex rules
- [ ] **Real-time feedback**: Validation as user types
- [ ] **Clear error messages**: Explains what's wrong
- [ ] **Submit button state**: Disabled until form valid

#### Modals & Dialogs
- [ ] **Confirmation modals**: Delete/bulk actions require confirmation
- [ ] **Keyboard navigation**: ESC closes, TAB cycles through elements
- [ ] **Focus management**: Focus trapped in modal when open
- [ ] **Backdrop click**: Closes modal (or prompts if unsaved changes)

#### Dropdowns & Menus
- [ ] **User menu**: Profile dropdown works
- [ ] **Action menus**: Per-item action dropdowns
- [ ] **Bulk actions**: Multi-select with bulk action dropdown
- [ ] **Keyboard accessible**: Arrow keys navigate, Enter selects

#### Live Updates
- [ ] **Auto-refresh toggle**: Audit log auto-refresh checkbox
- [ ] **Refresh interval**: Configurable refresh rate
- [ ] **Stat cards**: Dashboard stats update periodically
- [ ] **No full page reload**: AJAX updates where appropriate

**Test:**
```javascript
// Test password toggle
const toggle = document.querySelector('.password-toggle');
const input = document.querySelector('input[type="password"]');
toggle.click();
assert(input.type === 'text', 'Password not visible');
toggle.click();
assert(input.type === 'password', 'Password still visible');

// Test password entropy
const entropyDisplay = document.querySelector('.password-entropy');
input.value = 'weak';
input.dispatchEvent(new Event('input'));
assert(entropyDisplay.textContent.includes('Weak'), 'Entropy not calculated');
```

### 5. Forms & Input Elements

**Form consistency and usability**

#### Form Structure
- [ ] **Consistent layout**: All forms follow same pattern
- [ ] **Label placement**: Labels above inputs
- [ ] **Required indicators**: Asterisk or (required) text
- [ ] **Help text**: Explanatory text below inputs
- [ ] **Field grouping**: Related fields visually grouped

#### Input Types
- [ ] **Text inputs**: Standard text fields
- [ ] **Password inputs**: With toggle/entropy features
- [ ] **Email inputs**: HTML5 email type
- [ ] **Select dropdowns**: Consistent styling
- [ ] **Checkboxes**: Clear labels, proper spacing
- [ ] **Radio buttons**: Grouped options
- [ ] **Textareas**: Adequate height, resizable

#### Form Actions
- [ ] **Submit buttons**: Primary action clearly visible
- [ ] **Cancel links**: Secondary action (returns to previous page)
- [ ] **Reset buttons**: (If needed, clearly labeled)
- [ ] **Button states**: Loading state during submission
- [ ] **Success feedback**: Flash messages after successful submission
- [ ] **Error feedback**: Inline errors + flash messages

**Test:**
```bash
# Verify all forms have CSRF protection
rg '<form' src/netcup_api_filter/templates/ | \
  xargs -I {} sh -c "grep -L 'csrf_token' {}"
# Should return no results (all forms have CSRF)

# Verify submit buttons
rg 'type="submit"' src/netcup_api_filter/templates/ | wc -l
# Should match number of forms
```

### 6. Tables & Data Display

**Table consistency across list pages**

#### Table Structure
- [ ] **Responsive tables**: Horizontal scroll on mobile
- [ ] **Consistent columns**: Similar data types use same column width
- [ ] **Header row**: Clear column headers
- [ ] **Row hover**: Highlight on hover
- [ ] **Empty state**: Message when no data
- [ ] **Pagination**: For large datasets (if implemented)

#### Table Features
- [ ] **Sorting**: Clickable column headers (if implemented)
- [ ] **Filtering**: Search/filter functionality
- [ ] **Bulk selection**: Checkboxes for multi-select
- [ ] **Per-row actions**: Edit/delete icons or dropdown
- [ ] **Status badges**: Color-coded status indicators
- [ ] **Timestamps**: Consistent date/time formatting

#### Specific Tables
- [ ] **Accounts table**: Username, email, status, actions
- [ ] **Realms table**: Realm value, type, owner, actions
- [ ] **Tokens table**: Alias, prefix, realm, expiry, actions
- [ ] **Audit log table**: Timestamp, user, action, status, IP

**Test:**
```bash
# Verify all tables have thead/tbody structure
rg '<table' src/netcup_api_filter/templates/ | \
  xargs -I {} grep -L '<thead>' {}
# Should return no results

# Verify empty state messages
rg 'No .* found|Nothing to display' src/netcup_api_filter/templates/ | wc -l
# Should be > 5 (one per list page)
```

### 7. Dashboard & Statistics

**Files:** `admin/dashboard.html`, `account/dashboard.html`

#### Admin Dashboard Components
- [ ] **Stat cards**: Total accounts, realms, tokens, activity
- [ ] **Recent activity**: Last 10 activities list
- [ ] **Rate limited IPs**: List of rate-limited sources
- [ ] **Most active clients**: Top API usage
- [ ] **System status**: Backend health, database size
- [ ] **Quick actions**: Common admin tasks (create account, view logs)

#### Stat Card Design
- [ ] **Consistent layout**: All cards same structure
- [ ] **Icon/visual**: Meaningful icon per metric
- [ ] **Large number**: Prominently displayed
- [ ] **Description**: Clear label
- [ ] **Color coding**: Success/warning/danger colors
- [ ] **Clickable**: Links to detail page

#### Activity Feed
- [ ] **Reverse chronological**: Newest first
- [ ] **Activity type icons**: Visual distinction
- [ ] **User/realm context**: Shows who/what
- [ ] **Timestamp**: Relative time (e.g., "2 hours ago")
- [ ] **Status indicators**: Success/failure colors
- [ ] **Click to expand**: More details available

**Test:**
```python
# Test dashboard data loading
response = client.get('/admin/dashboard')
assert 'Total Accounts' in response.text
assert 'Total Realms' in response.text
assert 'Recent Activity' in response.text
```

### 8. Settings Pages

**Files:** `admin/settings.html`, related settings pages

#### Settings Categories
- [ ] **Email Settings**: SMTP configuration
  - [ ] Host, port, security (SSL/TLS/none)
  - [ ] Username, password
  - [ ] From email, from name
  - [ ] Test email button
- [ ] **GeoIP Settings**: MaxMind configuration
  - [ ] Account ID, license key
  - [ ] Edition IDs
  - [ ] Test lookup button
- [ ] **Rate Limits**: Per-endpoint limits
  - [ ] Admin portal limit
  - [ ] Account portal limit
  - [ ] API endpoint limit
  - [ ] Format validation (e.g., "50 per minute")
- [ ] **Security Settings**: Security policies
  - [ ] Password reset expiry
  - [ ] Invite expiry
  - [ ] 2FA enforcement

#### Settings Form Behavior
- [ ] **Current values**: Pre-filled with current settings
- [ ] **Password masking**: Passwords shown as dots with toggle
- [ ] **Test buttons**: Can test SMTP/GeoIP without saving
- [ ] **Validation**: Format validation before save
- [ ] **Save feedback**: Success message after save
- [ ] **Revert button**: Option to revert to defaults

**Test:**
```python
# Test settings update
response = client.post('/admin/settings/email', data={
    'smtp_host': 'smtp.example.com',
    'smtp_port': '587',
    'smtp_security': 'tls',
})
assert response.status_code == 200
assert 'Settings updated' in response.text

# Verify settings persisted
setting = get_setting('smtp_host')
assert setting == 'smtp.example.com'
```

### 9. Audit Log Viewer

**Files:** `admin/audit_logs.html`

#### Filtering Options
- [ ] **Time range**: Last hour, day, week, month, all time
- [ ] **Activity type**: Login, failed_auth, dns_update, etc.
- [ ] **Status**: Success, failure, error
- [ ] **User**: Filter by account
- [ ] **IP address**: Filter by source IP
- [ ] **Realm**: Filter by realm
- [ ] **Search**: Free-text search

#### Display Features
- [ ] **Expandable rows**: Click to see full details
- [ ] **JSON formatting**: Request/response data formatted
- [ ] **Syntax highlighting**: Color-coded JSON
- [ ] **Copy buttons**: Copy IP, user agent, etc.
- [ ] **Pagination**: Navigate through large logs
- [ ] **Export**: ODS export for offline analysis

#### Auto-Refresh
- [ ] **Toggle**: Checkbox to enable/disable auto-refresh
- [ ] **Interval**: Configurable refresh rate (default 30s)
- [ ] **Visual indicator**: Shows when refreshing
- [ ] **Scroll preservation**: Doesn't jump to top on refresh

**Test:**
```bash
# Test audit log filtering
curl -b "session=..." "http://localhost:5100/admin/audit-log?activity_type=login&status=success"
# Should return only successful login events

# Test ODS export
curl -b "session=..." "http://localhost:5100/admin/audit-log/export?format=ods" > audit.ods
file audit.ods
# Should be: OpenDocument Spreadsheet
```

### 10. Realm Templates

**Files:** `admin/realm_create.html`, JavaScript for template loading

#### Template Selection
- [ ] **6 pre-configured templates**: DDNS Single Host, DDNS Subdomain, Read-Only, LetsEncrypt, Full Management, CNAME Delegation
- [ ] **Template dropdown**: Clear names with icons
- [ ] **Template description**: Shows use case
- [ ] **Auto-fill**: Selecting template pre-fills form fields
- [ ] **Customizable**: Can modify template values before save

#### Template Accuracy
- [ ] **DDNS Single Host**:
  - Realm type: host
  - Record types: A, AAAA
  - Operations: read, update
- [ ] **DDNS Subdomain**:
  - Realm type: subdomain
  - Record types: A, AAAA, CNAME, TXT
  - Operations: read, create, update, delete
- [ ] **Read-Only Monitoring**:
  - Record types: All
  - Operations: read only
- [ ] **LetsEncrypt DNS-01**:
  - Realm type: subdomain
  - Record types: TXT only
  - Operations: read, create, delete
- [ ] **Full Management**:
  - Record types: All
  - Operations: All
- [ ] **CNAME Delegation**:
  - Realm type: subdomain
  - Record types: CNAME only
  - Operations: read, create, update, delete

**Test:**
```javascript
// Test template loading
const templateSelect = document.querySelector('#realm-template');
const recordTypesInput = document.querySelector('#record-types');

// Select "DDNS Single Host" template
templateSelect.value = 'ddns_single_host';
templateSelect.dispatchEvent(new Event('change'));

// Verify form updated
assert(recordTypesInput.value === 'A,AAAA', 'Template not applied');
```

### 11. Mobile Responsiveness

**Viewport breakpoints**

#### Mobile (< 768px)
- [ ] **Navbar collapses**: Hamburger menu
- [ ] **Tables scroll**: Horizontal scroll for wide tables
- [ ] **Cards stack**: Single column layout
- [ ] **Forms full-width**: Inputs span full width
- [ ] **Touch-friendly**: Buttons large enough for touch

#### Tablet (768px - 992px)
- [ ] **2-column layout**: Where appropriate
- [ ] **Navbar expanded**: Full navigation visible
- [ ] **Moderate padding**: Optimized for tablet

#### Desktop (> 992px)
- [ ] **Multi-column layouts**: 3-4 columns
- [ ] **Fixed navbar**: Sticky navigation
- [ ] **Sidebar**: (If implemented)

**Test:**
```javascript
// Test responsive navbar
function testNavbarResponsiveness() {
    // Simulate mobile viewport
    window.innerWidth = 375;
    window.dispatchEvent(new Event('resize'));
    
    const navbar = document.querySelector('.navbar-toggler');
    assert(navbar.offsetParent !== null, 'Hamburger not visible on mobile');
    
    // Simulate desktop viewport
    window.innerWidth = 1920;
    window.dispatchEvent(new Event('resize'));
    
    const navLinks = document.querySelector('.navbar-nav');
    assert(navLinks.offsetParent !== null, 'Nav links not visible on desktop');
}
```

### 12. Accessibility (WCAG 2.1 AA)

**Accessibility requirements**

#### Keyboard Navigation
- [ ] **Tab order**: Logical tab order through page
- [ ] **Focus indicators**: Visible focus outline on all interactive elements
- [ ] **Skip links**: Skip to main content link
- [ ] **Keyboard shortcuts**: Common actions accessible via keyboard

#### Screen Reader Support
- [ ] **Semantic HTML**: Proper use of header/nav/main/footer/article
- [ ] **ARIA labels**: aria-label on icons, buttons without text
- [ ] **ARIA live regions**: Dynamic content updates announced
- [ ] **Alt text**: All images have alt attributes
- [ ] **Form labels**: All inputs have associated labels

#### Color Contrast
- [ ] **Text contrast**: 4.5:1 minimum for body text
- [ ] **Large text contrast**: 3:1 minimum for large text (18pt+)
- [ ] **Interactive elements**: 3:1 contrast for buttons, links
- [ ] **Color not sole indicator**: Status shown with icons+text, not just color

#### Forms
- [ ] **Label association**: Labels linked to inputs (for/id)
- [ ] **Error identification**: Errors clearly identified
- [ ] **Error suggestions**: Helpful error messages
- [ ] **Required field indicators**: Clear marking of required fields

**Test:**
```bash
# Run automated accessibility audit (if axe-core available)
npx axe http://localhost:5100/admin/dashboard

# Manual keyboard navigation test
# 1. Tab through entire page
# 2. Verify all interactive elements reachable
# 3. Verify focus visible on all elements
# 4. Press Enter/Space on buttons
# 5. Use arrow keys in dropdowns
```

### 13. Performance

**Page load and runtime performance**

#### Load Time
- [ ] **First Contentful Paint**: < 1.5s
- [ ] **Largest Contentful Paint**: < 2.5s
- [ ] **Time to Interactive**: < 3.5s
- [ ] **Total page load**: < 5s

#### Optimization Techniques
- [ ] **CSS minification**: Minified CSS in production
- [ ] **JavaScript minification**: Minified JS in production
- [ ] **Image optimization**: Compressed images
- [ ] **Lazy loading**: Images loaded as needed
- [ ] **Font loading**: web fonts optimized
- [ ] **HTTP caching**: Cache headers set correctly

#### Runtime Performance
- [ ] **Smooth scrolling**: 60fps scrolling
- [ ] **Fast interactions**: < 100ms response to clicks
- [ ] **No jank**: Animations smooth
- [ ] **Efficient rendering**: No layout thrashing

**Test:**
```bash
# Test with Lighthouse
npx lighthouse http://localhost:5100/admin/dashboard --view

# Check performance score (should be 80+)
# Check accessibility score (should be 90+)
```

### 14. Error Handling & Feedback

**User feedback mechanisms**

#### Success Messages
- [ ] **Flash messages**: Green success banner after actions
- [ ] **Specific feedback**: "Account created" not just "Success"
- [ ] **Auto-dismiss**: Fades out after 5 seconds
- [ ] **Dismissible**: Can manually close

#### Error Messages
- [ ] **Flash messages**: Red error banner
- [ ] **Specific errors**: Explains what went wrong
- [ ] **Action items**: Suggests how to fix
- [ ] **Persistent**: Doesn't auto-dismiss (user must close)

#### Validation Errors
- [ ] **Inline errors**: Below invalid field
- [ ] **Error summary**: List of all errors at top
- [ ] **Field highlighting**: Invalid fields red border
- [ ] **Scroll to error**: Auto-scroll to first error

#### Loading States
- [ ] **Loading spinners**: On async operations
- [ ] **Disabled buttons**: Prevent double-submit
- [ ] **Progress indicators**: For long operations
- [ ] **Skeleton screens**: On page load (if implemented)

**Test:**
```python
# Test error display
response = client.post('/admin/accounts/create', data={
    'username': '',  # Invalid
    'password': 'weak',  # Invalid
})
assert 'Username is required' in response.text
assert 'Password too weak' in response.text

# Test success message
response = client.post('/admin/accounts/create', data={
    'username': 'testuser',
    'password': 'ValidPassword123!',
})
assert 'Account created successfully' in response.text
```

### 15. Visual Regression Testing

**Screenshot-based validation**

#### Screenshot Coverage
- [ ] **All admin pages**: Captured in light + dark mode
- [ ] **All account pages**: Captured in light + dark mode
- [ ] **Error pages**: 404, 500 captured
- [ ] **Modal states**: Open/closed states
- [ ] **Form states**: Empty, filled, error states

#### Baseline Management
- [ ] **Baseline images**: Stored in version control
- [ ] **Comparison tool**: Automated diff detection
- [ ] **Threshold**: Acceptable pixel difference defined
- [ ] **Review process**: Visual diffs reviewed before merge

#### Font Rendering
- [ ] **Consistent fonts**: Same fonts across environments
- [ ] **Emoji support**: Emojis render correctly (fonts-noto-color-emoji)
- [ ] **Icon fonts**: Bootstrap Icons load correctly

**Test:**
```bash
# Capture screenshots
./tooling/playwright/playwright-exec.sh python3 ui_tests/capture_ui_screenshots.py

# Compare to baseline (if tool available)
# ./tooling/compare-screenshots.sh deploy-local/screenshots/ baseline/

# Manual review
open deploy-local/screenshots/admin_dashboard.png
# Visually verify: layout, colors, fonts, spacing
```

## Expected Deliverable

**Comprehensive UI/UX review report:**

```markdown
# Admin UI & User Experience - UX Review

## Executive Summary
- UI completeness: ✅ Complete | ⚠️ Minor Gaps | ❌ Major Gaps
- Consistency: [score]/10
- Accessibility: WCAG [level]
- Performance: [Lighthouse score]
- Critical issues: [count]

## Page-by-Page Analysis

### Admin Dashboard
- Completeness: ✅/⚠️/❌
- Findings: [list]
- Screenshots: [attached]

### Accounts Management
...

[Continue for all pages]

## Design System Compliance

### Navigation
- Navbar consistency: ✅/⚠️/❌
- Issues: [list]

### Forms
- Consistency: ✅/⚠️/❌
- Validation quality: [score]
- Issues: [list]

### Tables
- Consistency: ✅/⚠️/❌
- Features: [list implemented]
- Missing: [list]

## Accessibility Audit

### WCAG 2.1 Level AA
- Perceivable: ✅/⚠️/❌
- Operable: ✅/⚠️/❌
- Understandable: ✅/⚠️/❌
- Robust: ✅/⚠️/❌

### Issues Found
1. [Issue] - Severity: [High/Medium/Low] - Location: [page]

## Performance Metrics

### Lighthouse Scores
- Performance: [score]/100
- Accessibility: [score]/100
- Best Practices: [score]/100
- SEO: [score]/100

### Load Time Analysis
- FCP: [time]ms
- LCP: [time]ms
- TTI: [time]ms

## Critical Issues (P0)
1. [Issue] - Page: [name] - Impact: [description] - Fix: [recommendation]

## UX Recommendations

### Immediate Improvements
1. [Action item with mockup/example]

### Long-term Enhancements
...

## Visual References
- [Screenshot showing issue]
- [Screenshot showing recommendation]

## Code References
- [File:line] - [Finding]
```

---

## Usage

```
Please perform a comprehensive UI/UX review using the checklist defined in .vscode/REVIEW_PROMPT_ADMIN_UI_UX.md.

Focus on:
1. Verifying all pages are complete and functional
2. Checking navigation and design consistency
3. Testing interactive elements and JavaScript
4. Evaluating accessibility compliance
5. Measuring performance metrics

Provide a structured report with screenshots, Lighthouse scores, and specific recommendations for improvements.
```
