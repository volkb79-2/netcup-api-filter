# UI Requirements Specification

**Version:** 2.0  
**Last Updated:** 2025-12-01  
**Status:** Draft for Review

---

## Table of Contents

1. [Design System Foundation](#1-design-system-foundation)
2. [Navigation & Layout](#2-navigation--layout)
3. [Admin Portal Pages](#3-admin-portal-pages)
4. [Account Portal Pages](#4-account-portal-pages) *(renamed from Client Portal)*
5. [Shared Components](#5-shared-components)
6. [API Endpoints Required](#6-api-endpoints-required)
7. [Database Schema](#7-database-schema)
8. [Authentication & Authorization](#8-authentication--authorization)
9. [Third-Party Integrations](#9-third-party-integrations)
10. [Implementation Phases](#10-implementation-phases)

---

## Architecture Overview

### Account → Realms → Tokens Model

The permission model uses a three-tier hierarchy:

```
Account (human user)
├── username (login identifier)
├── email (mandatory, verified)
├── password (for UI login)
├── 2FA (email mandatory, TOTP/Telegram optional)
│
├── Realms (what the account can access)
│   ├── Realm 1: subdomain:iot.example.com
│   │   └── record_types: [A, AAAA], operations: [R, U, C, D]
│   ├── Realm 2: host:vpn.example.com
│   │   └── record_types: [A], operations: [R, U]
│   └── Realm 3: subdomain_only:client1.vxxu.de
│       └── record_types: [A, AAAA, TXT], operations: [R, U, C, D]
│
└── Tokens (API credentials, multiple per realm)
    ├── Token 1: "home-router" → Realm 2
    │   └── ip_whitelist: [home-ip], expires: never, description: "Updates from home network"
    ├── Token 2: "monitoring" → Realm 1 (read-only subset)
    │   └── ops: [R], description: "Grafana dashboard queries"
    └── Token 3: "certbot" → Realm 1 (TXT only)
        └── record_types: [TXT], ops: [R, C, D], description: "Let's Encrypt automation"
```

### Realm Types

| Type | Pattern | Matches | Use Case |
|------|---------|---------|----------|
| `host` | `vpn.example.com` | Exact match only | Single host DDNS |
| `subdomain` | `iot.example.com` | `iot.example.com` + `*.iot.example.com` | Zone delegation |
| `subdomain_only` | `client1.vxxu.de` | `*.client1.vxxu.de` only (NOT apex) | Strict delegation |

### API Authentication

**Bearer token only** (simpler for machines):
```bash
curl -X POST https://naf.example.com/api/dns/update \
  -H "Authorization: Bearer naf_johndoe_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6" \
  -H "Content-Type: application/json" \
  -d '{"domain": "iot.example.com", "hostname": "device1", "type": "A", "destination": "192.168.1.100"}'
```

### Token Format

```
naf_<username>_<random64>
    ^^^^^^^^   ^^^^^^^^^^
    8-32 chars  64 chars (a-zA-Z0-9)

Examples:
  naf_johndoe_a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0u1V2w3X4y5Z6a7B8
  naf_iot-fleet_X9y8Z7w6V5u4T3s2R1q0P9o8N7m6L5k4J3i2H1g0F9e8D7c6B5a4
```

**Token structure:**
- `naf_` - Fixed prefix (4 chars)
- `<username>` - Account username (8-32 chars, lowercase alphanumeric + hyphen)
- `_` - Separator (1 char)
- `<random>` - Cryptographically random string (64 chars, `[a-zA-Z0-9]`)

**Total length:** 77-101 characters (well within HTTP header limits)

**Entropy:** 64 chars × log₂(62) ≈ 381 bits (extremely strong)

**Username embedded** → immediate routing/logging without database lookup
**Full token hashed** → bcrypt verification for authentication

---

## 1. Design System Foundation

### 1.1 Color Palette (Dark Blue-Black Theme)

```css
/* Primary Colors */
--color-bg-primary: #0a0e1a;      /* Deepest background */
--color-bg-secondary: #111827;    /* Card backgrounds */
--color-bg-elevated: #1a2234;     /* Elevated elements */
--color-bg-surface: rgba(26, 34, 52, 0.8);

/* Accent Colors */
--color-accent: #3b82f6;          /* Primary blue */
--color-accent-hover: #2563eb;    /* Hover state */

/* Status Colors */
--color-success: #10b981;         /* Green */
--color-warning: #f59e0b;         /* Amber */
--color-danger: #ef4444;          /* Red */
--color-info: #06b6d4;            /* Cyan */

/* Text Colors */
--color-text-primary: #f3f4f6;
--color-text-secondary: #9ca3af;
--color-text-muted: #6b7280;
```

### 1.2 Typography

| Element | Font | Size | Weight |
|---------|------|------|--------|
| H1 | System/Inter | 2rem | 600 |
| H2 | System/Inter | 1.5rem | 600 |
| H3 | System/Inter | 1.25rem | 600 |
| Body | System/Inter | 1rem | 400 |
| Monospace | JetBrains Mono/Consolas | 0.875rem | 400 |

**Monospace Fields:** Client ID, Realm Value, IP Ranges, Email Address, Tokens

### 1.3 Spacing Scale

```
xs: 0.5rem (8px)
sm: 0.75rem (12px)
md: 1rem (16px)
lg: 1.5rem (24px)
xl: 2rem (32px)
2xl: 3rem (48px)
```

### 1.4 Border Radius

```
sm: 0.375rem (6px)  - Buttons, inputs
md: 0.5rem (8px)    - Cards
lg: 0.75rem (12px)  - Modals
xl: 1rem (16px)     - Large panels
```

### 1.5 Theme System

The UI supports 6 color themes and 3 UI density modes, configurable via a dropdown in the navbar.

#### Available Themes

| Theme | Accent Color | Description |
|-------|--------------|-------------|
| **Cobalt 2** (default) | `#3b7cf5` Blue | Rich cobalt blue with bright borders and text |
| **Graphite** | `#3b82f6` Blue | Deep black with electric blue accents |
| **Obsidian Noir** | `#a78bfa` Violet | Ultra-dark with violet luxury |
| **Ember** | `#f97316` Orange | Warm charcoal with orange fire |
| **Jade** | `#34d399` Emerald | Rich black with emerald luxury |
| **Gold Dust** | `#fbbf24` Gold | Luxurious dark with gold accents |

#### UI Density Modes

| Mode | Card Gap | Table Padding | Use Case |
|------|----------|---------------|----------|
| **Comfortable** (default) | 1.5rem | 1rem | Normal usage, readability focus |
| **Compact** | 1rem | 0.625rem | Data-dense screens, more content visible |
| **Ultra Compact** | 0.75rem | 0.375rem | Maximum density, power users |

#### Theme Switcher Component

Located in navbar, to the left of username:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Logo] Netcup API Filter │ ... nav links ... │  🎨 ▼  │ admin ▼ │ Logout │
└─────────────────────────────────────────────────────────────────────────────┘
                                                   │
                                                   ▼
                                    ┌───────────────────────┐
                                    │ COLOR THEME           │
                                    │ ◉ Cobalt 2            │
                                    │ ○ Graphite            │
                                    │ ○ Obsidian Noir       │
                                    │ ○ Ember               │
                                    │ ○ Jade                │
                                    │ ○ Gold Dust           │
                                    ├───────────────────────┤
                                    │ UI DENSITY            │
                                    │ ◉ Comfortable         │
                                    │ ○ Compact             │
                                    │ ○ Ultra Compact       │
                                    └───────────────────────┘
```

#### Implementation Details

- **Persistence:** `localStorage` keys `naf-theme` and `naf-density`
- **Flash prevention:** Inline `<script>` in `<head>` applies classes before render
- **CSS Variables:** Themes override `:root` variables via `body.theme-*` classes
- **Alpine.js Store:** Manages state and provides reactive updates

```javascript
// Theme switcher Alpine.js store
Alpine.store('theme', {
    current: 'cobalt-2',
    density: 'comfortable',
    set(themeName) { /* applies theme class, saves to localStorage */ },
    setDensity(densityName) { /* applies density class, saves to localStorage */ }
});
```

---

## 2. Navigation & Layout

### 2.1 Top Navbar (Admin)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Logo] Netcup API Filter │ Dashboard │ Clients │ Audit Logs │ Netcup API │ Email │ System │     admin ▼ │ Logout │
└─────────────────────────────────────────────────────────────────────────────┘
                                                                        └── Dropdown: Change Password
```

**Specifications:**
- Height: 56px (compact)
- Sticky: Yes (fixed to top)
- Background: `--color-bg-secondary` with subtle border
- Active link: Accent color underline
- Username dropdown: "Change Password" option

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Logo] Netcup API Filter │ Dashboard │ Accounts │ Realms │ Audit │ Config ▼│  admin ▼ │ Logout │
└─────────────────────────────────────────────────────────────────────────────┘
                                                    └── Netcup API, Email, System
```

### 2.2 Top Navbar (Account Portal)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ [Logo] Netcup API Filter │ Dashboard │ Activity │                   johndoe ▼ │ Logout │
└─────────────────────────────────────────────────────────────────────────────┘
                                                                         └── Dropdown: Settings, Security, Logout
```

### 2.3 Page Layout Structure

```
┌───────────────────────────────────────────────────────────────┐
│                         NAVBAR                                │
├───────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─ Page Header ──────────────────────────────────────────┐   │
│  │ H1 Title                            [Action Buttons]   │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌─ Main Content ─────────────────────────────────────────┐   │
│  │                                                        │   │
│  │  Desktop: 2-3 column grid (content + sidebar)          │   │
│  │  Mobile: Single column stack                           │   │
│  │                                                        │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌─ Footer ───────────────────────────────────────────────┐   │
│  │ Build: v1.0.0 | © 2025                                 │   │
│  └────────────────────────────────────────────────────────┘   │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

---

## 3. Admin Portal Pages

### 3.1 Login Page (`/admin/login`)

**Current:** ✅ Acceptable baseline  
**Improvements:**
- Center form vertically
- Add subtle background gradient animation
- Show last login attempt info (if failed)

---

### 3.2 Change Password Page (`/admin/change-password`)

**Route:** `/admin/change-password`  
**Access:** Authenticated admin only  
**Redirect:** After initial password change → Logout → Login page with success message

**Layout:**
- monospace font in fields
- generate based on charset `[a-zA-Z0-9-=_+;:,.|/?@#$%^&*]`
- show entropy as color-coded badge 
```
┌────────────────────────────────────────────────────────┐
│                  Change Password                       │
├────────────────────────────────────────────────────────┤
│                                                        │
│  Current Password:                                     │
│  [__________________] 👁                               │
│                                                        │
│  New Password:                             [Generate]  │
│  [__________________] 👁                               │
│  Confirm Password:                                     │
│  [__________________] 👁                               │
│                                                        │
│           ---  Security Information ---                │
│  Character classes detected:           ┌──────────┐    │
│  ✓ Uppercase                           │ Entropy  │    │
│  ✓ Lowercase                           │   125    │    │
│  ✓ Number                              └──────────┘    │
│  ✓ Special character                                   │
│                                                        │
│           [Change Password]                            │
│                                                        │
└────────────────────────────────────────────────────────┘
```

**Behavior:**
- On success: Flash message, logout, redirect to login
- On initial change (password = default): Force change, no skip option

---

### 3.3 Dashboard Page (`/admin/`)

**Layout:**
```
┌─ Statistics Cards ────────────────────────────────────────────┐
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│ │ 12       │ │ 8        │ │ 156      │ │ 3        │          │
│ │ Accounts │ │ Active   │ │ API Calls│ │ Errors   │          │
│ │ Total    │ │ Today    │ │ (24h)    │ │ (24h)    │          │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
└───────────────────────────────────────────────────────────────┘

┌─ Pending Approvals ───────────────────────────────────────────┐
│ ⚠️ 2 account registrations pending                            │
│ ⚠️ 1 realm request pending                                    │
│                                        [Review Approvals →]   │
└───────────────────────────────────────────────────────────────┘

┌─ Quick Actions ───────────────────────────────────────────────┐
│ [+ New Account]  [View Audit Logs]  [Test Netcup API]         │
└───────────────────────────────────────────────────────────────┘

┌─ Recent Activity ─────────────────────────────────────────────┐
│ • Token "home-router" updated A record for home.example.com   │
│ • Token "certbot" created TXT for _acme.example.com           │
│ • SECURITY: Failed auth from 192.168.1.100 (15m ago)          │
│                                        [View All Logs →]      │
└───────────────────────────────────────────────────────────────┘
```

---

### 3.4 Accounts List Page (`/admin/accounts/`)

**Features:**
1. **Bulk Actions Bar** (when items selected):
   - Bulk Enable/Disable
   - Bulk Delete (with confirmation modal)

2. **Table Features:**
   - Client-side real-time filter (List.js) with info tooltip
   - Server-side search with pagination (50 items/page)
   - Sortable columns

3. **Row Actions:**
   - View Details (expand realms/tokens inline)
   - Edit Account
   - View Activity Log
   - Delete Account

**Table Columns:**
| Column | Width | Features |
|--------|-------|----------|
| ☐ (checkbox) | 40px | Bulk select |
| Status | 60px | Active/Pending/Disabled badge |
| Username | 150px | Monospace, link to details |
| Email | 200px | Verified badge ✓ |
| Realms | 150px | Count + expand icon |
| Tokens | 100px | Count (active/total) |
| Last Login | 120px | Relative time |
| Actions | 100px | View, Edit, Logs, Delete icons |

**Layout:**
```
┌─ Page Header ─────────────────────────────────────────────────┐
│ Accounts                                 [+ Create Account]   │
└───────────────────────────────────────────────────────────────┘

┌─ Pending Approvals (if any) ──────────────────────────────────┐
│ ⚠️ 2 registrations pending approval          [Review All →]   │
└───────────────────────────────────────────────────────────────┘

┌─ Bulk Actions (shown when selected) ──────────────────────────┐
│ 3 selected: [Enable] [Disable] [Delete]         [Clear]       │
└───────────────────────────────────────────────────────────────┘

┌─ Search & Filter ─────────────────────────────────────────────┐
│ [🔍 Quick filter...] ⓘ Client-side only                       │
│ [Server Search: ________] [Status: All ▼] [Search]            │
└───────────────────────────────────────────────────────────────┘

┌─ Table ───────────────────────────────────────────────────────┐
│ ☐ │ Status │ Username     │ Email             │ Realms│Tokens │
├───┼────────┼──────────────┼───────────────────┼───────┼───────┤
│ ☐ │ 🟢     │ `johndoe`    │ john@ex.com ✓     │ 3     │ 5/6   │
│ ☐ │ 🟡     │ `alice_dev`  │ alice@co.com ✓    │ 0     │ 0/0   │
│ ☐ │ 🔴     │ `old_user`   │ old@ex.com ✓      │ 1     │ 0/2   │
└───────────────────────────────────────────────────────────────┘

┌─ Pagination ──────────────────────────────────────────────────┐
│ Showing 1-50 of 156       [◀ Prev] [1] [2] [3] [4] [Next ▶]   │
└───────────────────────────────────────────────────────────────┘
```

---

### 3.4.1 Account Approval Queue (`/admin/accounts/pending`)

```
┌─ Pending Account Registrations ──────────────────────────────────────────────┐
│                                                              [Approve All]   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ☐ johndoe                                                                   │
│    Email: john@example.com ✓ verified                                        │
│    Requested: 2025-12-01 14:32                                               │
│    [Approve] [Reject with reason...]                                         │
│                                                                              │
│  ☐ alice_dev                                                                 │
│    Email: alice@company.com ✓ verified                                       │
│    Requested: 2025-12-01 10:15                                               │
│    [Approve] [Reject with reason...]                                         │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### 3.4.2 Realm Request Queue (`/admin/realms/pending`)

```
┌─ Pending Realm Requests ─────────────────────────────────────────────────────┐
│                                                                              │
│  ┌─ Request from: johndoe ───────────────────────────────────────────────┐   │
│  │  Realm: subdomain_only:client1.vxxu.de                                │   │
│  │  Record Types: A, AAAA, TXT                                           │   │
│  │  Operations: Read, Update, Create, Delete                             │   │
│  │  Requested: 2025-12-01 15:00                                          │   │
│  │                                                                       │   │
│  │  [Approve] [Modify & Approve] [Reject with reason...]                 │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### 3.5 Account Create Page (`/admin/accounts/new`)

**Admin-created accounts bypass email verification and approval.**

```
┌─ Create Account ─────────────────────────────────────────────────────────────┐
│                                                                              │
│  ─── Account Details ───                                                     │
│                                                                              │
│  Username *            `[________________]`                                  │
│                        Letters, numbers, underscore. 3-64 chars.             │
│                                                                              │
│  Email *               `[________________]`                                  │
│                        Will be marked as verified automatically.             │
│                                                                              │
│  Temporary Password *  [________________] [Generate]                         │
│                        User will be forced to change on first login.        │
│                                                                              │
│  Notification Email    `[________________]` (optional, for alerts)           │
│                                                                              │
│  ─── Initial Realm (optional) ───                                            │
│                                                                              │
│  ☐ Create with initial realm                                                 │
│                                                                              │
│  (If checked, show realm configuration form)                                 │
│                                                                              │
│  [Create Account]  [Cancel]                                                  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### 3.5.1 Realm Create/Assign Page (`/admin/accounts/<id>/realms/new`)

**Two-Step Wizard:**

#### Step 1: Template Selection (Visual Cards)

```
┌─ Select Configuration Template ───────────────────────────────┐
│                                                               │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │      🏠        │  │      🌐        │  │      �        │  │
│  │ DDNS Single    │  │ DDNS Subdomain │  │ Subdomain      │  │
│  │ Host           │  │ Delegation     │  │ Only           │  │
│  │                │  │                │  │                │  │
│  │ Realm: host    │  │ Realm:subdomain│  │ Realm:         │  │
│  │                │  │                │  │ subdomain_only │  │
│  │ Records:       │  │ Records:       │  │                │  │
│  │ [A] [AAAA]     │  │ [A][AAAA][CNAME]│ │ Records:       │  │
│  │ ─────────────  │  │ ─────────────  │  │ [A][AAAA][TXT] │  │
│  │ Permissions:   │  │ Permissions:   │  │ ─────────────  │  │
│  │ [R] [U]        │  │ [R][C][U][D]   │  │ Permissions:   │  │
│  │                │  │                │  │ [R][C][U][D]   │  │
│  │ [Select]       │  │ [Select]       │  │ [Select]       │  │
│  └────────────────┘  └────────────────┘  └────────────────┘  │
│                                                               │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │      👁️        │  │      🔐        │  │      ⚙️        │  │
│  │ Read-Only      │  │ LetsEncrypt    │  │ Full DNS       │  │
│  │ Monitoring     │  │ DNS-01         │  │ Management     │  │
│  │                │  │                │  │                │  │
│  │ Realm: host    │  │ Realm:subdomain│  │ Realm: host    │  │
│  │                │  │                │  │                │  │
│  │ Records:       │  │ Records:       │  │ Records:       │  │
│  │ [All types]    │  │ [TXT]          │  │ [All types]    │  │
│  │ ─────────────  │  │ ─────────────  │  │ ─────────────  │  │
│  │ Permissions:   │  │ Permissions:   │  │ Permissions:   │  │
│  │ [R]            │  │ [R] [C] [D]    │  │ [R][C][U][D]   │  │
│  │                │  │                │  │                │  │
│  │ [Select]       │  │ [Select]       │  │ [Select]       │  │
│  └────────────────┘  └────────────────┘  └────────────────┘  │
│                                                               │
│              [Skip Template - Custom Configuration]           │
└───────────────────────────────────────────────────────────────┘
```

**Template Card Details:**
- Icon (emoji)
- Name
- Realm type indicator
- Record types section (labeled "Records:", badges)
- Separator line (─────────────)
- Operations section (labeled "Permissions:", badges)
- Use cases (hover tooltip or expand)
- Example realm value

#### Step 2: Realm Details Form

**UI Element Notation:**
- `[Button]` - Clickable button
- `[Text ▼]` - Dropdown select
- `[___]` - Text input field
- `☐` / `☑` - Checkbox
- `[○───]` / `[───●]` - Toggle slider (off/on)
- `(monospace)` - Use monospace font

```
┌─ Realm Configuration ──────────────────────────────────────────┐
│                                                                │
│  Account: johndoe (john@example.com)                           │
│  Template: 🏠 DDNS Single Host                                 │
│                                                                │
│  ─── Realm ───                                                 │
│                                                                │
│  Realm Type *       [Host ▼] [Subdomain ▼] [Subdomain Only ▼]  │
│  Realm Value *      `[example.com________]` (monospace)        │
│                                                                │
│  ─── Permissions ───                                           │
│                                                                │
│  Allowed Record Types *                                        │
│  [A] [AAAA] [CNAME] [TXT] [MX] [NS] [SRV] [SSHFP]              │
│                                                                │
│  Allowed Operations *                                          │
│  [Read] [Create] [Update] [Delete]                             │
│                                                                │
│  [Assign Realm]  [Cancel]                                      │
│                                                                │
└────────────────────────────────────────────────────────────────┘

┌─ Sidebar ──────────────────────────────────────────────────────┐
│ ┌─ Realm Type Explained ────────────────────────────────────┐  │
│ │                                                           │  │
│ │ **host**: Exact match only                                │  │
│ │   ✅ vpn.example.com                                      │  │
│ │   ❌ sub.vpn.example.com                                  │  │
│ │                                                           │  │
│ │ **subdomain**: Apex + all children                        │  │
│ │   ✅ iot.example.com                                      │  │
│ │   ✅ device1.iot.example.com                              │  │
│ │                                                           │  │
│ │ **subdomain_only**: Children only (NOT apex)              │  │
│ │   ❌ client1.vxxu.de (apex excluded)                      │  │
│ │   ✅ host1.client1.vxxu.de                                │  │
│ │                                                           │  │
│ └───────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

**Form Validation (Real-time):**
- Realm Value: domain syntax validation
- At least one record type selected
- At least one operation selected

#### Step 2.1: Compact Realm Form (Single-Page Layout)

**Design Goal:** Maximize information density while maintaining usability. Uses 2-column grid layout for related fields.

```
┌─ Realm Configuration (full width) ───────────────────────────────────────────┐
│                                                                              │
│  Account: johndoe                                                            │
│                                                                              │
│  ┌─ Left Column ─────────────────────┐  ┌─ Right Column ─────────────────┐   │
│  │                                   │  │                                │   │
│  │  Realm Type *     [Subdomain ▼]   │  │  Realm Value *                 │   │
│  │                                   │  │  `[iot.example.com______]`     │   │
│  │  Available types:                 │  │                                │   │
│  │  • host (exact match)             │  │                                │   │
│  │  • subdomain (apex + children)    │  │                                │   │
│  │  • subdomain_only (children only) │  │                                │   │
│  └───────────────────────────────────┘  └────────────────────────────────┘   │
│                                                                              │
│  ─── Permissions ────────────────────────────────────────────────────────    │
│                                                                              │
│  ┌─ Record Types * ──────────────────┐  ┌─ Operations * ─────────────────┐   │
│  │  [A]    [AAAA]   [CNAME]  [TXT]   │  │  [Read]   [Create]             │   │
│  │  [MX]   [NS]     [SRV]    [SSHFP] │  │  [Update] [Delete]             │   │
│  └───────────────────────────────────┘  └────────────────────────────────┘   │
│                                                                              │
│  [Assign Realm]  [Cancel]                                                    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### 3.6 Token Create Page (`/account/realms/<id>/tokens/new`)

**Users create their own tokens for their realms.**

```
┌─ Create API Token ─────────────────────────────────────────────┐
│                                                                │
│  Realm: subdomain:iot.example.com                              │
│  Available: A, AAAA | Read, Update, Create, Delete             │
│                                                                │
│  ─── Token Details ───                                         │
│                                                                │
│  Token Name *       `[home-router___________]`                 │
│                     Unique identifier for this token           │
│                                                                │
│  Description        [Updates A record from home network___]    │
│                     Human-readable purpose                     │
│                                                                │
│  ─── Scope (optional restrictions) ───                         │
│                                                                │
│  Record Types       [A] [AAAA] (subset of realm, or leave all) │
│  Operations         [Read] [Update] (subset of realm)          │
│                                                                │
│  ─── Security ───                                              │
│                                                                │
│  Allowed IPs        `[192.168.1.0/24_________]` (one per line) │
│                     Leave empty for no restriction             │
│                                                                │
│  Expires            [Never ▼] [1 month] [3 months] [1 year]    │
│                     [📅 Custom date: ___________]              │
│                                                                │
│  [Create Token]  [Cancel]                                      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

### 3.6.1 Token Created Success Page

**One-time view after token creation:**

```
┌─────────────────────────────────────────────────────────────────┐
│                    ✅ Token Created Successfully                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Token Name:   `home-router`                                    │
│  Realm:        subdomain:iot.example.com                        │
│                                                                 │
│  ┌─ API Token ────────────────────────────────────────────────┐│
│  │                                                            ││
│  │  ⚠️ IMPORTANT: This token will NOT be shown again!        ││
│  │                                                            ││
│  │  `naf_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6`          [📋 Copy] ││
│  │                                                            ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                 │
│  ─── Quick Start ───                                            │
│                                                                 │
│  Example API call:                                              │
│  ┌────────────────────────────────────────────────────────────┐│
│  │ curl -X POST https://naf.example.com/api/dns/update \      ││
│  │   -H "Authorization: Bearer naf_a1b2c3d4..." \             ││
│  │   -H "Content-Type: application/json" \                    ││
│  │   -d '{"domain":"iot.example.com",                         ││
│  │        "hostname":"device1","type":"A",                    ││
│  │        "destination":"192.168.1.100"}'                     ││
│  └────────────────────────────────────────────────────────────┘│
│                                                       [📋 Copy] │
│                                                                 │
│  [Back to Dashboard]  [Create Another Token]                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

### 3.7 Audit Logs Page (`/admin/auditlog/`)

**Features:**
1. **Filters:**
   - Time range: Last Hour / 24h / 7 days / 30 days / Custom
   - Status: All / Success / Failure
   - Client: Dropdown (All + each client)
   - Action type: infoDnsRecords, updateDnsRecords, etc.

2. **Data Management:**
   - Trim logs: Delete older than X days
   - Clear all logs (with confirmation)
   - Export to ODS

3. **Auto-Update:**
   - Toggle slider: "Auto-refresh every 2s"
   - Only table content refreshes (AJAX)

4. **Expandable Rows:**
   - Click row to expand details
   - Show full request/response JSON

**Layout:**
```
┌─ Page Header ─────────────────────────────────────────────────┐
│ Audit Logs                    [Export ODS ▼] [Trim...] [Clear]│
└───────────────────────────────────────────────────────────────┘

┌─ Filters ─────────────────────────────────────────────────────┐
│ Time: [Last 24h ▼]  Status: [All ▼]  Client: [All ▼]          │
│ Action: [All ▼]  [🔍 Search...]                    [Apply]    │
│                                                               │
│ Auto-refresh: [═══○───] Off                                   │
└───────────────────────────────────────────────────────────────┘

┌─ Table ───────────────────────────────────────────────────────┐
│ Timestamp         │ Client      │ Action          │ Status    │
├───────────────────┼─────────────┼─────────────────┼───────────┤
│▶ 2025-11-30 14:32│ client_ddns │ updateDnsRecords│ ✅ Success│
│  └─ Details: {"hostname":"home.example.com","ip":"1.2.3.4"}  │
│▶ 2025-11-30 14:30│ client_cert │ infoDnsRecords  │ ✅ Success│
│▶ 2025-11-30 14:28│ unknown     │ login           │ ❌ Failed │
│  └─ IP: 192.168.1.100, Reason: Invalid token                 │
└───────────────────────────────────────────────────────────────┘

┌─ Pagination ──────────────────────────────────────────────────┐
│ Showing 1-50 of 1,234        [◀] [1] [2] [3] ... [25] [▶]     │
│ Applied filters: Last 24h                                     │
└───────────────────────────────────────────────────────────────┘
```

**Trim Logs Modal:**
```
┌─ Trim Audit Logs ─────────────────────────────────────────────┐
│                                                               │
│  Delete logs older than: [30] days                            │
│                                                               │
│  This will delete approximately 5,432 log entries.            │
│                                                               │
│  [Cancel]                                      [Delete Logs]  │
└───────────────────────────────────────────────────────────────┘
```

---

### 3.8 Netcup API Config Page (`/admin/netcup_config/`)

**Current:** ✅ Good baseline (see attached screenshot)

**Improvements:**
- Add "Test Connection" button
- Show connection status indicator
- Password field: show/hide toggle (👁)
- Add last successful connection timestamp

**Layout:**
```
┌─ Main Form ────────────────────────────────────────────────────┐
│ API Credentials                                                │
│                                                                │
│  Customer ID:    [________________________]                    │
│  API Key:        [________________________] 👁                 │
│  API Password:   [________________________] 👁                 │
│  API URL:        [https://ccp.netcup.net/...]                  │
│  Timeout (sec):  [30]                                          │
│                                                                │
│  [Save Configuration]  [Test Connection]                       │
│                                                                │
│  Status: ✅ Connected (last tested: 2 min ago)                 │
└────────────────────────────────────────────────────────────────┘
```

---

### 3.9 Email Config Page (`/admin/email_config/`)

**Current:** ✅ Good baseline (see attached screenshot)

**Improvements:**
1. Reorder fields (sender email first)
2. Add "Query Autoconfiguration" button
3. Add sender name field
4. Add email template editor
5. Granular notification settings

**Layout:**
```
┌─ SMTP Settings ────────────────────────────────────────────────┐
│                                                                │
│  Sender Email:   [admin@example.com_______] [🔍 Autoconfig]    │
│  Sender Name:    [Netcup API Filter_______]                    │
│                                                                │
│  SMTP Server:    [smtp.example.com________]                    │
│  SMTP Port:      [465]  (465=SSL, 587=TLS)                     │
│  Username:       [________________________] 👁                 │
│  Password:       [________________________] 👁                 │
│  ☑ Use SSL/TLS                                                 │
│                                                                │
│  [Save] [Test SMTP Connection]                                 │
└────────────────────────────────────────────────────────────────┘

┌─ Admin Notifications ──────────────────────────────────────────┐
│  Admin Email:    [security@example.com____]                    │
│                                                                │
│  Notify on:                                                    │
│  ☑ Security events (failed logins, IP blocks)                  │
│  ☑ Client lockouts                                             │
│  ☐ Token expiration warnings (7 days before)                   │
│  ☐ System errors                                               │
└────────────────────────────────────────────────────────────────┘

┌─ Email Template ───────────────────────────────────────────────┐
│  Subject: [Netcup API Filter: {{ event.type }}]                │
│                                                                │
│  Body: (basic HTML formatting, Thunderbird dark mode compatible)│
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ <h2>{{ event.title }}</h2>                               │ │
│  │ <p>{{ event.description }}</p>                           │ │
│  │ <p><strong>Time:</strong> {{ event.timestamp }}</p>      │ │
│  │ <p><strong>Client:</strong> {{ event.client_id }}</p>    │ │
│  │ <p><strong>IP:</strong> {{ event.source_ip }}</p>        │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  Note: Uses basic HTML elements only (h2, p, strong)           │
│  No inline styles or background colors for dark mode compat    │
│                                                                │
│  Available variables: {{ event.type }}, {{ event.title }},     │
│  {{ event.description }}, {{ event.timestamp }},               │
│  {{ event.client_id }}, {{ event.source_ip }},                 │
│  {{ event.details }}                                           │
│                                                                │
│  [Save Template] [Preview] [Reset to Default]                  │
└────────────────────────────────────────────────────────────────┘

┌─ Test Email ───────────────────────────────────────────────────┐
│  Send to:        [test@example.com________]                    │
│                                         [Send Test Email]      │
└────────────────────────────────────────────────────────────────┘
```

---

### 3.10 System Info Page (`/admin/systeminfo/`)

**Layout:**
```
┌─ System Health ────────────────────────────────────────────────┐
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│ │ ✅       │ │ 45ms     │ │ 2.3 MB   │ │ 1,234    │           │
│ │ API OK   │ │ Avg Resp │ │ DB Size  │ │ Clients  │           │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘           │
└────────────────────────────────────────────────────────────────┘

┌─ Build Information ────────────────────────────────────────────┐
│  Version:        1.0.0                                         │
│  Build Date:     2025-11-30T14:00:00Z                          │
│  Git Commit:     abc123def                                     │
│  Python:         3.11.5                                        │
└────────────────────────────────────────────────────────────────┘

┌─ Dependencies ─────────────────────────────────────────────────┐
│  Flask:          3.0.0                                         │
│  Flask-Admin:    2.0.2                                         │
│  SQLAlchemy:     2.0.23                                        │
│  ... (collapsible list)                                        │
└────────────────────────────────────────────────────────────────┘

┌─ Settings ─────────────────────────────────────────────────────┐
│  Session Timeout: [1440] minutes  (default: 1440 = 24h)        │
│  Applies to: Admin & Client sessions                          │
│                                              [Save Settings]   │
└────────────────────────────────────────────────────────────────┘

┌─ Actions ──────────────────────────────────────────────────────┐
│  [Restart Application]  [Download Logs]  [Cleanup Database]    │
└────────────────────────────────────────────────────────────────┘
```

---

## 4. Account Portal Pages

*(Renamed from Client Portal - now serves user accounts with multiple realms/tokens)*

### 4.0 Account Registration Flow

#### 4.0.1 Registration Page (`/register`)

```
┌─ Create Account ─────────────────────────────────────────────────────────────┐
│                                                                              │
│  Step 1 of 3: Account Details                                                │
│  ───────────────────────────────────────────────────────────────────────     │
│                                                                              │
│  Username *            `[________________]`                                  │
│                        Letters, numbers, underscore. 3-64 chars.             │
│                                                                              │
│  Email *               `[________________]`                                  │
│                        Used for login verification and notifications.        │
│                                                                              │
│  Password *            [________________] [👁]                               │
│                        Min 12 chars, mix of upper/lower/number/symbol.       │
│                                                                              │
│  Confirm Password *    [________________] [👁]                               │
│                                                                              │
│                                                     [Continue →]             │
│                                                                              │
│  Already have an account? [Login]                                            │
└──────────────────────────────────────────────────────────────────────────────┘
```

#### 4.0.2 Email Verification (`/register/verify`)

```
┌─ Verify Email ───────────────────────────────────────────────────────────────┐
│                                                                              │
│  Step 2 of 3: Email Verification                                             │
│  ───────────────────────────────────────────────────────────────────────     │
│                                                                              │
│  We sent a 6-digit code to:                                                  │
│  📧 john@example.com                                                         │
│                                                                              │
│  Verification Code *   `[______]`                                            │
│                                                                              │
│  Code expires in: 9:42                                                       │
│                                                                              │
│  Didn't receive it? [Resend Code] (available in 2 minutes)                   │
│                                                                              │
│                                                     [Verify →]               │
└──────────────────────────────────────────────────────────────────────────────┘
```

#### 4.0.3 Pending Approval (`/register/pending`)

```
┌─ Pending Approval ───────────────────────────────────────────────────────────┐
│                                                                              │
│  Step 3 of 3: Admin Approval                                                 │
│  ───────────────────────────────────────────────────────────────────────     │
│                                                                              │
│  ✅ Email verified successfully!                                             │
│                                                                              │
│  Your account is pending admin approval.                                     │
│  You will receive an email when your account is activated.                   │
│                                                                              │
│  Account: johndoe                                                            │
│  Email: john@example.com                                                     │
│  Requested: December 1, 2025 14:32                                           │
│                                                                              │
│                                                     [Back to Login]          │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### 4.1 Account Login Page (`/account/login`)

**Two-step authentication:**

```
┌─ Login ──────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  Username              `[________________]`                                  │
│  Password              [________________] [👁]                               │
│                                                                              │
│                                                     [Continue →]             │
│                                                                              │
│  [Forgot Password?]                    [Create Account]                      │
└──────────────────────────────────────────────────────────────────────────────┘
```

**After password verification → 2FA step:**

```
┌─ Two-Factor Authentication ──────────────────────────────────────────────────┐
│                                                                              │
│  A verification code has been sent to j***@example.com                       │
│                                                                              │
│  Code *                `[______]`                                            │
│                                                                              │
│  ☐ Remember this device for 30 days                                         │
│                                                                              │
│                                                     [Verify →]               │
│                                                                              │
│  [Use TOTP Authenticator instead]  (if TOTP enabled)                         │
│  [Use Telegram instead]            (if Telegram linked)                      │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### 4.2 Account Dashboard (`/account/dashboard`)

**Main dashboard showing all realms and tokens:**

```
┌─ Account Dashboard ──────────────────────────────────────────────────────────┐
│                                                                              │
│  Welcome, johndoe                                    [Settings] [Logout]     │
│  Email: john@example.com ✓ verified                                          │
│                                                                              │
├─ My Realms ──────────────────────────────────────────────────────────────────┤
│                                                        [+ Request New Realm] │
│                                                                              │
│  ┌─ iot.example.com (subdomain) ─────────────────────────────────────────┐  │
│  │  Records: A AAAA TXT  |  Perms: R U C D                     [Manage]  │  │
│  │                                                                       │  │
│  │  ▼ Tokens (2)                                              [+ New]    │  │
│  │  ┌────────────────────────────────────────────────────────────────┐   │  │
│  │  │  🔑 home-router                                                │   │  │
│  │  │  "Updates A record from home network"                          │   │  │
│  │  │  ┌─────────────────────────────────┬──────────────────────────┐│   │  │
│  │  │  │ Created: 2025-11-01             │ Access by Source IP      ││   │  │
│  │  │  │ Last used: 2 hours ago          │ ───────────────────────  ││   │  │
│  │  │  │ Scope: A AAAA | R U             │ 203.0.113.50:    47 calls││   │  │
│  │  │  │ IP: 203.0.113.0/24              │ 203.0.113.51:    12 calls││   │  │
│  │  │  │ Expires: Never                  │                          ││   │  │
│  │  │  │                                 │                          ││   │  │
│  │  │  │ [Timeline] [Regenerate] [Edit] [Revoke]                    ││   │  │
│  │  │  └─────────────────────────────────┴──────────────────────────┘│   │  │
│  │  └────────────────────────────────────────────────────────────────┘   │  │
│  │  ┌────────────────────────────────────────────────────────────────┐   │  │
│  │  │  🔑 certbot-prod                                               │   │  │
│  │  │  "ACME DNS-01 challenge from production server"                │   │  │
│  │  │  ┌─────────────────────────────────┬──────────────────────────┐│   │  │
│  │  │  │ Created: 2025-10-15             │ Access by Source IP      ││   │  │
│  │  │  │ Last used: 30 days ago          │ ───────────────────────  ││   │  │
│  │  │  │ Scope: TXT | R C D              │ 10.0.0.5:         3 calls││   │  │
│  │  │  │ IP: any                         │                          ││   │  │
│  │  │  │ Expires: 2026-01-01             │                          ││   │  │
│  │  │  │                                 │                          ││   │  │
│  │  │  │ [Timeline] [Regenerate] [Edit] [Revoke]                    ││   │  │
│  │  │  └─────────────────────────────────┴──────────────────────────┘│   │  │
│  │  └────────────────────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─ vpn.example.com (host) ──────────────────────────────────────────────┐  │
│  │  Records: A  |  Perms: R U                                  [Manage]  │  │
│  │                                                                       │  │
│  │  ▼ Tokens (1)                                              [+ New]    │  │
│  │  ┌────────────────────────────────────────────────────────────────┐   │  │
│  │  │  🔑 vpn-updater                                                │   │  │
│  │  │  "Dynamic IP update for VPN endpoint"                          │   │  │
│  │  │  ┌─────────────────────────────────┬──────────────────────────┐│   │  │
│  │  │  │ Last used: 1 hour ago           │ Access by Source IP      ││   │  │
│  │  │  │ Scope: A | R U                  │ ───────────────────────  ││   │  │
│  │  │  │ IP: any                         │ 185.12.34.56:   102 calls││   │  │
│  │  │  │ Expires: Never                  │ 185.12.34.57:     8 calls││   │  │
│  │  │  │                                 │                          ││   │  │
│  │  │  │ [Timeline] [Regenerate] [Edit] [Revoke]                    ││   │  │
│  │  │  └─────────────────────────────────┴──────────────────────────┘│   │  │
│  │  └────────────────────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─ client1.vxxu.de (subdomain_only) ─ ⏳ Pending Approval ──────────────┐  │
│  │  Requested: 2025-11-30  |  Records: A AAAA TXT  |  Perms: R U C D     │  │
│  │  Status: Awaiting admin approval                                      │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### 4.3 Account Settings Page (`/account/settings`)

```
┌─ Account Settings ─────────────────────────────────────────────────────────┐
│                                                                            │
├─ Profile ──────────────────────────────────────────────────────────────────┤
│                                                                            │
│  Username:           johndoe (cannot be changed)                           │
│  Email:              john@example.com ✓                   [Change Email]   │
│  Notification Email: `[alerts@example.com___]`           (optional)        │
│  Created:            2025-11-15                                            │
│  Last Login:         2025-12-01 14:30                                      │
│                                                                            │
│                                                        [Save Changes]      │
├─ Security ─────────────────────────────────────────────────────────────────┤
│                                                                            │
│  Password                                              [Change Password]   │
│                                                                            │
│  Two-Factor Authentication:                                                │
│  ✅ Email 2FA (mandatory)                                                  │
│  ☐ TOTP Authenticator                                  [Enable TOTP]      │
│  ☐ Telegram                                            [Link Telegram]    │
│                                                                            │
├─ Notifications ────────────────────────────────────────────────────────────┤
│                                                                            │
│  Notify me when:                                                           │
│  ☑ Token used from new IP                                                  │
│  ☑ Failed authentication attempt                                          │
│  ☐ Successful authentication (high volume)                                │
│  ☑ Token expiring soon (7 days before)                                    │
│  ☑ Realm request approved/rejected                                        │
│                                                                            │
│                                                        [Save Preferences]  │
├─ Danger Zone ──────────────────────────────────────────────────────────────┤
│                                                                            │
│  ⚠️ Delete Account                                                         │
│  This will revoke all tokens and delete all data.                          │
│                                              [Delete My Account]           │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

---

### 4.4 Token Timeline Page (`/account/tokens/<id>/activity`)

**Activity log filtered to a specific token:**

```
┌─ Token Timeline: home-router ────────────────────────────────────────────────┐
│                                                                              │
│  Realm: iot.example.com (subdomain)                                          │
│  Description: Updates A record from home network                             │
│  Scope: A AAAA | Read Update                                                 │
│                                                                              │
├─ Filters ────────────────────────────────────────────────────────────────────┤
│  Date: [Last 7 days ▼]  Status: [All ▼]  IP: [All ▼]      [Export] [Refresh]│
└──────────────────────────────────────────────────────────────────────────────┘

┌─ Activity ───────────────────────────────────────────────────────────────────┐
│                                                                              │
│  ● 14:32 - 30.11.2025                  updateDnsRecords  ✅                  │
│  │ source: 203.0.113.50 [🌍 GeoIP]     Updated A: device1.iot.example.com    │
│  │                                     → 192.168.1.100                       │
│  │                                                                           │
│  ● 14:30 - 30.11.2025                  infoDnsRecords   ✅                   │
│  │ source: 203.0.113.50 [🌍 GeoIP]     Read 3 records                        │
│  │                                                                           │
│  ● 14:25 - 30.11.2025                  updateDnsRecords   ❌ DENIED          │
│  │ source: 203.0.222.22 [🌍 GeoIP]     IP not in whitelist                   │
│  │                                                                           │
│  ● 12:00 - 30.11.2025                  updateDnsRecords  ✅                  │
│  │ source: 203.0.113.50                Updated AAAA: device1.iot.example.com │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

### 4.5 Realm DNS Records Page (`/account/realms/<id>/dns`)

**Features:**
- List all records within the realm scope
- Quick "Update to My IP" action for A/AAAA records
- Create/Edit/Delete based on realm permissions

```
┌─ DNS Records for home.example.com ─────────────────────────────┐
│                                        [+ Add Record] (if perm)│
└────────────────────────────────────────────────────────────────┘

┌─ Your Current IP ──────────────────────────────────────────────┐
│  Detected: 203.0.113.50 (Public IPv4)                          │
└────────────────────────────────────────────────────────────────┘

┌─ Records ──────────────────────────────────────────────────────┐
│                                                                │
│  A Record                                                      │
│  ├─ Host: home.example.com                                     │
│  ├─ Value: 192.168.1.100                                       │
│  ├─ TTL: 300                                                   │
│  └─ Actions: [Update to My IP] [Edit] [Delete]                 │
│                                                                │
│  AAAA Record                                                   │
│  ├─ Host: home.example.com                                     │
│  ├─ Value: 2001:db8::1                                         │
│  ├─ TTL: 300                                                   │
│  └─ Actions: [Update to My IP] [Edit] [Delete]                 │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

### 4.6 Client Record Create/Edit Page

**Features:**
- "Fill with My IP" button for A/AAAA records
- Two options: Public IP (always available) + Local IP (greyed out if unavailable)
- Real-time validation

```
┌─ Create A Record ──────────────────────────────────────────────┐
│                                                                │
│  Record Type:    A                                             │
│  Hostname:       [home.example.com_____]                       │
│  Value (IP):     [___________________] [My Public IP] [My Local IP]│
│  TTL:            [300]                                         │
│                                                                │
│  Detected IPs:                                                 │
│  • Public: 203.0.113.50 (always available from server)         │
│  • Local: 192.168.1.100 (greyed out if unavailable)            │
│                                                                │
│  [Save Record]  [Cancel]                                       │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

**IP Detection Behavior:**
- **Public IP:** Always available (server-side detection via `request.remote_addr`)
- **Local IP:** Detected via WebRTC if browser supports; button disabled/greyed if unavailable

---

## 5. Shared Components

### 5.1 Tables

**All tables include:**
- Client-side filter (List.js) with tooltip: "ⓘ Filters visible rows only"
- Server-side search for full dataset
- Sortable columns (click header)
- Pagination (50 items/page)
- Responsive: horizontal scroll on mobile

### 5.2 Status Badges

| Status | Color | Icon |
|--------|-------|------|
| Active | Green | 🟢 |
| Inactive | Red | 🔴 |
| Pending | Yellow | 🟡 |
| Success | Green | ✅ |
| Failed | Red | ❌ |
| Warning | Amber | ⚠️ |

### 5.3 Buttons

| Type | Use Case | Style |
|------|----------|-------|
| Primary | Main action | Blue, solid |
| Secondary | Secondary action | Gray, solid |
| Outline | Tertiary | Border only |
| Danger | Delete, destructive | Red |
| Success | Save, confirm | Green |

### 5.4 Form Elements

- **Text inputs:** Dark bg, subtle border, focus glow
- **Selects:** Custom styled dropdowns
- **Multiselect:** Compact checkbox/tag style
- **Checkboxes:** Toggle switches for boolean
- **Textareas:** Resizable, monospace option

### 5.5 Modals

- Centered, overlay backdrop
- Max-width: 500px for forms, 800px for details
- Close on Escape, click outside

### 5.6 Toast Notifications

- Position: Top-right
- Auto-dismiss: 5s for success, persist for errors
- Types: Success, Error, Warning, Info

---

## 6. API Endpoints Required

### 6.1 Admin API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/admin/api/accounts` | List all accounts with pagination |
| GET | `/admin/api/accounts/search` | Server-side account search |
| POST | `/admin/api/accounts/bulk` | Bulk enable/disable/delete |
| POST | `/admin/api/accounts/<id>/approve` | Approve pending account |
| POST | `/admin/api/accounts/<id>/reject` | Reject pending account |
| GET | `/admin/api/realms/pending` | List pending realm requests |
| POST | `/admin/api/realms/<id>/approve` | Approve realm request |
| POST | `/admin/api/realms/<id>/reject` | Reject realm request |
| POST | `/admin/api/audit/trim` | Delete logs older than X days |
| DELETE | `/admin/api/audit/clear` | Delete all logs |
| GET | `/admin/api/audit/export` | Export logs to ODS |
| POST | `/admin/api/email/test-smtp` | Test SMTP connection |
| POST | `/admin/api/email/autoconfig` | Query email autoconfiguration |
| GET | `/admin/api/system/restart` | Touch restart file |
| GET | `/admin/api/system/logs` | Download application logs |

### 6.2 Authentication Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/register` | Registration form |
| POST | `/register` | Submit registration |
| POST | `/register/verify` | Verify email code |
| GET | `/register/pending` | Pending approval page |
| GET | `/login` | Login form |
| POST | `/login` | Login step 1 (credentials) |
| POST | `/login/2fa` | Login step 2 (2FA code) |
| POST | `/logout` | End session |

### 6.3 Account Portal API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/account` | Account dashboard data |
| PUT | `/account` | Update account settings |
| GET | `/account/realms` | List user's realms |
| POST | `/account/realms` | Request new realm |
| GET | `/account/realms/<id>/dns` | List DNS records for realm |
| POST | `/account/tokens` | Create new token for realm |
| DELETE | `/account/tokens/<id>` | Revoke token |
| GET | `/account/tokens/<id>/activity` | Token activity timeline |
| GET | `/account/activity/export` | Export activity to ODS |

### 6.4 Public API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/geoip/<ip>` | GeoIP lookup |
| GET | `/api/myip` | Return caller's public IP |

### 6.5 DNS Proxy API (Bearer Token Auth)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/dns/<domain>/records` | List DNS records |
| POST | `/api/dns/<domain>/records` | Create record |
| PUT | `/api/dns/<domain>/records/<id>` | Update record |
| DELETE | `/api/dns/<domain>/records/<id>` | Delete record |

---

## 7. Database Schema

### 7.1 Accounts Table (replaces clients)

### Username Validation Rules

```
Length:    8-32 characters
Charset:   a-z (lowercase), 0-9, hyphen (-)
Format:    Must start with letter, cannot end with hyphen
Reserved:  admin, root, system, api, naf, test (configurable)

Valid:     johndoe, iot-fleet-mgr, device01, my-home-router
Invalid:   JohnDoe (uppercase), -start (starts with hyphen), 
           ab (too short), 01user (starts with number)
```

```sql
-- User Accounts (humans who log into UI)
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY,
    username VARCHAR(32) UNIQUE NOT NULL,       -- Login identifier, 8-32 chars
    email VARCHAR(255) UNIQUE NOT NULL,         -- Mandatory, verified
    email_verified INTEGER DEFAULT 0,
    password_hash VARCHAR(255) NOT NULL,        -- bcrypt for UI login
    
    -- 2FA (email mandatory, others optional)
    totp_secret VARCHAR(32),                    -- NULL = TOTP not enabled
    totp_enabled INTEGER DEFAULT 0,
    email_2fa_enabled INTEGER DEFAULT 1,        -- Mandatory
    telegram_chat_id VARCHAR(64),               -- NULL = Telegram not linked
    telegram_enabled INTEGER DEFAULT 0,
    
    -- Notifications (separate from login email)
    notification_email VARCHAR(255),            -- Optional, for alerts
    notify_new_ip INTEGER DEFAULT 1,
    notify_failed_auth INTEGER DEFAULT 1,
    notify_successful_auth INTEGER DEFAULT 0,
    notify_token_expiring INTEGER DEFAULT 1,
    notify_realm_status INTEGER DEFAULT 1,
    
    -- Status
    is_active INTEGER DEFAULT 0,                -- Requires admin approval
    is_admin INTEGER DEFAULT 0,
    approved_by INTEGER REFERENCES accounts(id),
    approved_at DATETIME,
    
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    last_login_at DATETIME,
    
    CHECK(email_2fa_enabled = 1 OR totp_enabled = 1 OR telegram_enabled = 1)
);

-- Username is already UNIQUE, which creates an implicit index
-- Additional index for email lookup
CREATE INDEX idx_account_email ON accounts(email);
```

### 7.2 Account Realms Table

```sql
-- Realms (what an account can access)
CREATE TABLE account_realms (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    
    realm_type VARCHAR(20) NOT NULL,            -- 'host', 'subdomain', 'subdomain_only'
    realm_value VARCHAR(255) NOT NULL,
    
    allowed_record_types TEXT NOT NULL,         -- JSON array: ["A", "AAAA", ...]
    allowed_operations TEXT NOT NULL,           -- JSON array: ["read", "update", ...]
    
    -- Request/approval workflow
    status VARCHAR(20) DEFAULT 'pending',       -- 'pending', 'approved', 'rejected'
    requested_at DATETIME NOT NULL,
    approved_by INTEGER REFERENCES accounts(id),
    approved_at DATETIME,
    rejection_reason TEXT,
    
    created_at DATETIME NOT NULL,
    
    UNIQUE(account_id, realm_type, realm_value),
    CHECK(realm_type IN ('host', 'subdomain', 'subdomain_only')),
    CHECK(status IN ('pending', 'approved', 'rejected'))
);
```

### 7.3 API Tokens Table

```sql
-- API Tokens (machine credentials, scoped to realm)
CREATE TABLE api_tokens (
    id INTEGER PRIMARY KEY,
    realm_id INTEGER NOT NULL REFERENCES account_realms(id) ON DELETE CASCADE,
    
    token_name VARCHAR(64) NOT NULL,            -- Human label: "aws-lambda-updater"
    token_description TEXT,                     -- "Updates host1 A record from AWS"
    token_prefix VARCHAR(8) NOT NULL,           -- First 8 chars of random part for lookup
    token_hash VARCHAR(255) NOT NULL,           -- bcrypt(full_token including username)
    
    -- Scope restrictions (subset of realm permissions, NULL = inherit)
    allowed_record_types TEXT,                  -- JSON array, NULL = use realm's
    allowed_operations TEXT,                    -- JSON array, NULL = use realm's
    allowed_ip_ranges TEXT,                     -- JSON array, NULL = no restriction
    
    expires_at DATETIME,                        -- NULL = never
    last_used_at DATETIME,
    last_used_ip VARCHAR(45),
    use_count INTEGER DEFAULT 0,
    
    is_active INTEGER DEFAULT 1,
    created_at DATETIME NOT NULL,
    revoked_at DATETIME,
    revoked_reason TEXT,
    
    UNIQUE(realm_id, token_name)
);

-- Index for token lookup: account username (from token) → prefix
CREATE INDEX idx_token_lookup ON api_tokens(token_prefix);
```

### 7.4 Activity Log Table

```sql
-- Activity Log (per-token audit trail)
CREATE TABLE activity_log (
    id INTEGER PRIMARY KEY,
    token_id INTEGER REFERENCES api_tokens(id) ON DELETE SET NULL,
    account_id INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
    
    action VARCHAR(50) NOT NULL,                -- 'api_call', 'login', 'token_created', etc.
    operation VARCHAR(20),                      -- 'read', 'update', 'create', 'delete'
    
    realm_type VARCHAR(20),
    realm_value VARCHAR(255),
    record_type VARCHAR(10),
    record_name VARCHAR(255),
    
    source_ip VARCHAR(45) NOT NULL,
    user_agent TEXT,
    
    status VARCHAR(20) NOT NULL,                -- 'success', 'denied', 'error'
    status_reason TEXT,                         -- "IP not whitelisted", "Token expired"
    
    request_data TEXT,                          -- JSON: sanitized request details
    response_summary TEXT,                      -- JSON: result summary
    
    created_at DATETIME NOT NULL
);

CREATE INDEX idx_activity_token ON activity_log(token_id, created_at);
CREATE INDEX idx_activity_account ON activity_log(account_id, created_at);
CREATE INDEX idx_activity_ip ON activity_log(source_ip, created_at);
```

### 7.5 Registration Requests Table

```sql
-- Pending registrations (before email verification)
CREATE TABLE registration_requests (
    id INTEGER PRIMARY KEY,
    username VARCHAR(64) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    
    verification_code VARCHAR(6) NOT NULL,
    verification_expires_at DATETIME NOT NULL,
    verification_attempts INTEGER DEFAULT 0,
    
    created_at DATETIME NOT NULL,
    
    CHECK(verification_attempts <= 5)
);
```

### 7.6 Settings Table

```sql
CREATE TABLE settings (
    id INTEGER PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,
    value TEXT,
    updated_at DATETIME NOT NULL
);
```

---

## 8. Authentication & Authorization

### 8.1 UI Authentication (Accounts)

**Login Flow:**
1. Username + Password → validate credentials
2. 2FA challenge (email code, TOTP, or Telegram)
3. Session created with configurable timeout

**2FA Options:**
| Method | Implementation | Cost | Notes |
|--------|---------------|------|-------|
| Email | SMTP (existing) | Free | Mandatory default |
| TOTP | `pyotp` library | Free | Google Authenticator compatible |
| Telegram | Bot API | Free | Optional, instant delivery |

### 8.2 API Authentication (Tokens)

**Bearer Token Format:**
```
Authorization: Bearer naf_johndoe_a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8s9T0u1V2w3X4y5Z6a7B8
               ^^^^^^ ^^^ ^^^^^^^ ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
               scheme pfx username 64 random characters [a-zA-Z0-9]
```

**Token Parsing:**
```python
import re

TOKEN_PATTERN = re.compile(r'^naf_([a-z][a-z0-9-]{6,30}[a-z0-9])_([a-zA-Z0-9]{64})$')

def parse_token(token: str) -> tuple[str, str] | None:
    """Parse token into (username, random_part) or None if invalid."""
    match = TOKEN_PATTERN.match(token)
    if not match:
        return None
    return match.group(1), match.group(2)
```

**Token Lookup:**
1. Parse token → extract `username` and `random_part`
2. Find account by username (indexed)
3. Find token by account_id + first 8 chars of random (indexed)
4. Verify full token against bcrypt hash
5. Check token active, not expired, IP allowed
6. Check realm approved
7. Check operation + record type permitted

### 8.3 Permission Resolution

```python
def check_permission(token, operation, domain, record_type):
    # 1. Token → Realm → Account chain must be valid
    realm = token.realm
    account = realm.account
    
    if not account.is_active:
        return Denied("Account disabled")
    if realm.status != 'approved':
        return Denied("Realm not approved")
    if not token.is_active:
        return Denied("Token revoked")
    if token.expires_at and token.expires_at < now():
        return Denied("Token expired")
    
    # 2. IP whitelist check (token-level)
    if token.allowed_ip_ranges:
        if not ip_in_ranges(request.remote_addr, token.allowed_ip_ranges):
            return Denied("IP not whitelisted")
    
    # 3. Realm match
    if not realm_matches(domain, realm.realm_type, realm.realm_value):
        return Denied("Domain not in realm scope")
    
    # 4. Operation check (token overrides realm if specified)
    allowed_ops = token.allowed_operations or realm.allowed_operations
    if operation not in allowed_ops:
        return Denied("Operation not permitted")
    
    # 5. Record type check (token overrides realm if specified)
    allowed_types = token.allowed_record_types or realm.allowed_record_types
    if record_type not in allowed_types:
        return Denied("Record type not permitted")
    
    return Granted()
```

---

## 9. Third-Party Integrations

### 9.1 MaxMind GeoIP

**Documentation:**
- https://dev.maxmind.com/geoip/geolocate-an-ip/web-services/
- https://dev.maxmind.com/geoip/docs/web-services/requests/
- https://dev.maxmind.com/geoip/docs/web-services/responses/

**Configuration:**
```
# .env.defaults
MAXMIND_LICENSE_KEY=your_license_key_here
MAXMIND_ACCOUNT_ID=your_account_id
```

**Usage:**
- Web Services API (not downloadable database)
- Called on-demand when user clicks "IP Info" button
- Cache responses for 24 hours to minimize API calls

### 9.2 ODS Export

**Library:** `odfpy`

ODF Python library for reading and writing OpenDocument files (ODS spreadsheets).
Simple implementation for exporting tabular data to ODS format.

**Add to requirements.webhosting.txt:**
```
odfpy>=1.4.1
```

### 9.3 Telegram Bot API (2FA)

**Documentation:**
- https://core.telegram.org/bots/api
- https://core.telegram.org/bots#how-do-i-create-a-bot

**Configuration:**
```
# .env.defaults
TELEGRAM_BOT_TOKEN=          # From @BotFather
TELEGRAM_2FA_ENABLED=false   # Enable Telegram as 2FA option
```

**Setup Flow (User):**
1. User clicks "Enable Telegram 2FA" in Account Settings
2. System shows QR code / link to bot (`t.me/YourBotName?start=<link_code>`)
3. User opens Telegram, sends `/start` with link code
4. Bot receives update, links Telegram chat_id to account
5. Confirmation shown in UI

**2FA Flow:**
1. User logs in with username + password
2. System sends code via Telegram: `🔐 Your login code: 847291`
3. User enters code in UI
4. Session created

**Implementation:**
```python
import httpx

async def send_telegram_2fa(chat_id: str, code: str):
    """Send 2FA code via Telegram Bot API."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        raise ConfigurationError("TELEGRAM_BOT_TOKEN not set")
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    response = await httpx.post(url, json={
        "chat_id": chat_id,
        "text": f"🔐 Your login code: {code}\n\nValid for 5 minutes.",
        "parse_mode": "HTML"
    })
    response.raise_for_status()
```

**Cost:** Free for all message volumes

### 9.4 TOTP (Time-based One-Time Password)

**Library:** `pyotp`

**Add to requirements.webhosting.txt:**
```
pyotp>=2.9.0
```

**Setup Flow (User):**
1. User clicks "Enable TOTP" in Account Settings
2. System generates secret, shows QR code
3. User scans with Google Authenticator / Authy
4. User enters code to verify setup
5. Recovery codes shown (one-time download)

**Implementation:**
```python
import pyotp
import qrcode
import io
import base64

def generate_totp_secret() -> str:
    """Generate new TOTP secret."""
    return pyotp.random_base32()

def get_totp_uri(secret: str, username: str, issuer: str = "NAF") -> str:
    """Generate TOTP provisioning URI for QR code."""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(name=username, issuer_name=issuer)

def verify_totp(secret: str, code: str) -> bool:
    """Verify TOTP code with 30-second window tolerance."""
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)

def generate_qr_code_base64(uri: str) -> str:
    """Generate QR code as base64 data URI for embedding."""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return f"data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}"
```

---

## 10. Implementation Phases

### Phase 1: Database & Core Auth (Week 1)

- [ ] Create new database schema (accounts, realms, tokens, activity_log)
- [ ] Implement account registration flow with email verification
- [ ] Implement login with email 2FA (mandatory)
- [ ] Session management with configurable timeout
- [ ] Password hashing with bcrypt

### Phase 2: Admin Portal - Account Management (Week 2)

- [ ] Dashboard with Accounts/Tokens/Realms/Pending stats
- [ ] Accounts list with approval status, 2FA badges
- [ ] Account create wizard with templates
- [ ] Account approval workflow
- [ ] Realm request approval/rejection

### Phase 3: Account Portal - Self-Service (Week 3)

- [ ] Account dashboard with realm list
- [ ] Token management (create, revoke, view)
- [ ] Request new realm flow
- [ ] Account settings (email, password, 2FA)
- [ ] Activity timeline (token-grouped)

### Phase 4: API Authentication (Week 4)

- [ ] Bearer token validation middleware
- [ ] Permission resolution (Account → Realm → Token chain)
- [ ] IP whitelist enforcement
- [ ] Token usage tracking (last_used, use_count)
- [ ] Activity logging for all API calls

### Phase 5: Enhanced 2FA Options (Week 5)

- [ ] TOTP setup with QR code generation
- [ ] TOTP verification in login flow
- [ ] Telegram Bot API integration
- [ ] Telegram linking flow
- [ ] Recovery codes for TOTP

### Phase 6: Advanced Features (Week 6)

- [ ] DNS record management for realms
- [ ] MaxMind GeoIP integration
- [ ] ODS export for audit logs
- [ ] Email notifications (token expiry, failed logins)
- [ ] Bulk operations for admin

### Phase 7: Polish & Testing (Week 7)

- [ ] Mobile responsiveness testing
- [ ] Accessibility review
- [ ] Update UI regression test baselines
- [ ] Performance optimization
- [ ] Security audit

---

## Appendix A: Template Definitions

Templates provide pre-configured realm settings for common use cases.

| ID | Name | Icon | Realm Type | Records | Operations | Use Case |
|----|------|------|------------|---------|------------|----------|
| ddns_single_host | DDNS Single Host | 🏠 | host | A, AAAA | read, update | Home router DDNS |
| ddns_subdomain_zone | DDNS Subdomain | 🌐 | subdomain | A, AAAA, CNAME | full | IoT fleet DDNS |
| ddns_subdomain_only | DDNS Children Only | 🔒 | subdomain_only | A, AAAA | read, update | Strict delegation |
| monitoring_readonly | Read-Only | 👁️ | host | all | read | Monitoring |
| letsencrypt_dns01 | LetsEncrypt | 🔒 | subdomain_only | TXT | read, create, delete | DNS-01 challenge |
| full_management | Full Management | ⚙️ | host | all | full | CI/CD automation |
| cname_only | CNAME Delegation | 🔗 | subdomain | CNAME | full | CDN/load balancer |

**Template Application:**
- User selects template → realm config pre-populated
- User can modify before submission
- Admin sees which template was used during approval

---

## Appendix B: Notification Events

| Event | Description | Recipient | Default |
|-------|-------------|-----------|---------|
| `account.registered` | New registration needs approval | Admin | On |
| `account.approved` | Account approved | User | On |
| `account.disabled` | Account disabled | User | On |
| `realm.approved` | Realm request approved | User | On |
| `realm.rejected` | Realm request rejected | User | On |
| `token.expiring` | Token expires in 7 days | User | On |
| `token.expired` | Token has expired | Admin | Off |
| `auth.failed_login` | Failed authentication attempt | User | Off |
| `auth.new_device` | Login from new IP/device | User | On |
| `api.ip_blocked` | Access from non-whitelisted IP | User | On |
| `api.permission_denied` | API call denied | User (log only) | Off |

---

*End of UI Requirements Specification*
