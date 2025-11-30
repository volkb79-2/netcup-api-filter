#!/usr/bin/env python3
"""
Analyze UI screenshots and generate inspection report with optimization recommendations.

This script examines screenshot metadata and generates a comprehensive report
for UI/UX review and workflow optimization.
"""
from pathlib import Path
from PIL import Image
import json


def analyze_screenshot(screenshot_path: Path) -> dict:
    """Analyze a single screenshot and extract metadata."""
    try:
        with Image.open(screenshot_path) as img:
            return {
                "path": str(screenshot_path),
                "name": screenshot_path.stem,
                "size": img.size,
                "width": img.width,
                "height": img.height,
                "format": img.format,
                "mode": img.mode,
                "file_size_kb": screenshot_path.stat().st_size / 1024,
            }
    except Exception as e:
        return {
            "path": str(screenshot_path),
            "name": screenshot_path.stem,
            "error": str(e)
        }


def categorize_pages(screenshots: list) -> dict:
    """Categorize screenshots by page type."""
    categories = {
        "public": [],
        "admin": [],
        "client": [],
    }
    
    for screenshot in screenshots:
        name = screenshot["name"]
        if "login" in name:
            categories["public"].append(screenshot)
        elif name.startswith("0") and "admin" in name:
            categories["admin"].append(screenshot)
        elif name.startswith("0") and "client" in name:
            categories["client"].append(screenshot)
        else:
            # Determine by prefix
            if any(x in name for x in ["admin", "audit", "netcup", "email", "system"]):
                categories["admin"].append(screenshot)
            else:
                categories["client"].append(screenshot)
    
    return categories


def generate_workflow_analysis(categories: dict) -> list:
    """Generate workflow analysis and recommendations."""
    recommendations = []
    
    # Admin workflow analysis
    admin_pages = categories.get("admin", [])
    if admin_pages:
        recommendations.append({
            "category": "Admin Workflow",
            "observation": f"Captured {len(admin_pages)} admin pages",
            "pages": [p["name"] for p in admin_pages],
            "considerations": [
                "Dashboard should provide quick access to most common tasks",
                "Client management is primary workflow - ensure easy navigation",
                "Configuration pages should have clear Save/Test buttons",
                "System info useful for troubleshooting - ensure comprehensive data",
            ]
        })
    
    # Client workflow analysis
    client_pages = categories.get("client", [])
    if client_pages:
        recommendations.append({
            "category": "Client Portal Workflow",
            "observation": f"Captured {len(client_pages)} client pages",
            "pages": [p["name"] for p in client_pages],
            "considerations": [
                "Dashboard should show domains and quick stats at a glance",
                "Domain detail page is primary workspace - optimize for common operations",
                "Record management should support bulk operations where appropriate",
                "Activity log helps clients verify their actions - ensure clear formatting",
            ]
        })
    
    # Responsive design analysis
    avg_width = sum(s["width"] for s in sum(categories.values(), []) if "width" in s) / max(len(sum(categories.values(), [])), 1)
    recommendations.append({
        "category": "Responsive Design",
        "observation": f"Average screenshot width: {avg_width:.0f}px",
        "considerations": [
            "Test on mobile devices (320px - 768px width)",
            "Ensure tables scroll horizontally on small screens",
            "Consider card layout for mobile dashboard",
            "Touch-friendly button sizes (min 44x44px)",
        ]
    })
    
    # UI consistency analysis
    recommendations.append({
        "category": "UI Consistency",
        "considerations": [
            "Consistent header/navigation across all pages",
            "Uniform button styles (primary/secondary/danger)",
            "Consistent form field layouts and validation messages",
            "Matching card styles for dashboard statistics",
            "Consistent footer with version/copyright info",
        ]
    })
    
    # Accessibility analysis
    recommendations.append({
        "category": "Accessibility",
        "considerations": [
            "Sufficient color contrast (WCAG AA: 4.5:1 for normal text)",
            "Keyboard navigation support (tab through forms)",
            "Clear focus indicators on interactive elements",
            "Alt text for any icons or images",
            "Form labels properly associated with inputs",
        ]
    })
    
    # Performance optimization
    recommendations.append({
        "category": "Performance",
        "considerations": [
            "Minimize JavaScript payload (current: Alpine.js + Bootstrap)",
            "Lazy load large tables (pagination or infinite scroll)",
            "Cache static assets (CSS/JS) with versioning",
            "Consider server-side rendering for initial page load",
            "Optimize database queries for audit log pagination",
        ]
    })
    
    return recommendations


def generate_page_specific_notes() -> dict:
    """Generate specific notes for each page type."""
    return {
        "00-admin-login": [
            "Should show clear branding/logo",
            "Password field with show/hide toggle?",
            "Remember me checkbox needed?",
            "Link to client portal login?",
        ],
        "00-client-login": [
            "Simple token input - one field is good",
            "Clear instructions for where to get token",
            "Link back to admin if user has wrong page?",
        ],
        "01-admin-dashboard": [
            "Show key metrics: total clients, active clients, recent logs",
            "Quick action buttons for common tasks",
            "Recent activity/audit log preview",
            "System health indicators?",
        ],
        "02-admin-clients-list": [
            "Table with: ID, description, realm, operations, status",
            "Search/filter by client ID or domain",
            "Bulk actions (activate/deactivate)?",
            "Clear indication of active vs inactive",
        ],
        "03-admin-client-create": [
            "Clear field labels and help text",
            "Realm type selector with examples",
            "Multi-select for operations and record types",
            "Token generation preview?",
            "IP whitelist with CIDR notation help",
        ],
        "04-admin-audit-logs": [
            "Searchable/filterable table",
            "Date range picker for filtering",
            "Export to CSV functionality?",
            "Color coding for success/failure",
            "Expandable rows for full details",
        ],
        "05-admin-netcup-config": [
            "Secure password field (masked)",
            "Test connection button with clear feedback",
            "API URL with default pre-filled",
            "Timeout configuration",
        ],
        "06-admin-email-config": [
            "SMTP settings with standard ports",
            "Test email button with recipient input",
            "Enable/disable per feature (admin/client notifications)",
            "Email template preview?",
        ],
        "07-admin-system-info": [
            "Python version and packages",
            "Database location and size",
            "Log file paths and sizes",
            "Environment variables (sanitized)",
            "Filesystem access test results",
        ],
        "08-client-dashboard": [
            "Domain cards with record counts",
            "Recent activity summary",
            "Token permissions reminder",
            "Quick links to manage domains",
        ],
        "09-client-activity-log": [
            "Filterable by date/operation",
            "Clear timestamps",
            "Success/failure indicators",
            "Details of what changed",
        ],
        "10-client-domain-detail": [
            "Zone info at top",
            "Searchable records table",
            "Sortable columns",
            "Inline edit or modal forms?",
            "Bulk operations (delete multiple records)?",
        ],
    }


def main():
    """Main analysis workflow."""
    print("🔍 Analyzing UI Screenshots")
    print("=" * 80)
    
    # Find all screenshots (NO HARDCODED PATHS)
    screenshot_dir_path = os.environ.get('SCREENSHOT_DIR')
    if not screenshot_dir_path:
        repo_root = os.environ.get('REPO_ROOT')
        if not repo_root:
            raise RuntimeError("SCREENSHOT_DIR or REPO_ROOT must be set (no hardcoded paths allowed)")
        screenshot_dir_path = f"{repo_root}/screenshots"
        print(f"⚠️  WARNING: SCREENSHOT_DIR not set, using: {screenshot_dir_path}")
    
    screenshot_dir = Path(screenshot_dir_path)
    if not screenshot_dir.exists():
        print(f"❌ Screenshot directory not found: {screenshot_dir}")
        return
    
    screenshots = []
    for screenshot_path in sorted(screenshot_dir.glob("*.png")):
        print(f"  📊 Analyzing {screenshot_path.name}...")
        screenshots.append(analyze_screenshot(screenshot_path))
    
    print(f"\n✅ Analyzed {len(screenshots)} screenshots")
    
    # Categorize pages
    categories = categorize_pages(screenshots)
    
    # Generate report
    print("\n" + "=" * 80)
    print("UI INSPECTION REPORT")
    print("=" * 80)
    
    # Page counts by category
    print("\n📊 PAGE INVENTORY")
    print("-" * 80)
    for category, pages in categories.items():
        print(f"  {category.upper()}: {len(pages)} pages")
        for page in pages:
            size_info = f"{page['width']}x{page['height']}px, {page['file_size_kb']:.1f}KB" if 'width' in page else 'Error'
            print(f"    • {page['name']}: {size_info}")
    
    # Screenshot statistics
    print("\n📐 SCREENSHOT STATISTICS")
    print("-" * 80)
    all_pages = sum(categories.values(), [])
    if all_pages:
        valid_pages = [p for p in all_pages if 'width' in p]
        if valid_pages:
            avg_width = sum(p['width'] for p in valid_pages) / len(valid_pages)
            avg_height = sum(p['height'] for p in valid_pages) / len(valid_pages)
            total_size = sum(p['file_size_kb'] for p in valid_pages)
            print(f"  Average dimensions: {avg_width:.0f}x{avg_height:.0f}px")
            print(f"  Total size: {total_size:.1f}KB")
            print(f"  Average size per page: {total_size/len(valid_pages):.1f}KB")
    
    # Workflow analysis
    print("\n🔄 WORKFLOW ANALYSIS & RECOMMENDATIONS")
    print("-" * 80)
    workflow_recs = generate_workflow_analysis(categories)
    for rec in workflow_recs:
        print(f"\n{rec['category'].upper()}")
        if 'observation' in rec:
            print(f"  Observation: {rec['observation']}")
        if 'pages' in rec:
            print(f"  Pages: {', '.join(rec['pages'])}")
        print("  Considerations:")
        for consideration in rec['considerations']:
            print(f"    • {consideration}")
    
    # Page-specific notes
    print("\n📝 PAGE-SPECIFIC OPTIMIZATION NOTES")
    print("-" * 80)
    page_notes = generate_page_specific_notes()
    for page_name, notes in page_notes.items():
        # Check if we have this page
        if any(s['name'] == page_name for s in all_pages):
            print(f"\n{page_name}:")
            for note in notes:
                print(f"  • {note}")
    
    # Missing pages/features
    print("\n⚠️  POTENTIALLY MISSING PAGES/FEATURES")
    print("-" * 80)
    print("  • Client password change page (if admin changed token)")
    print("  • Admin password reset/recovery flow")
    print("  • Bulk client import/export (CSV)")
    print("  • API documentation page (for clients)")
    print("  • Health check/status endpoint page")
    print("  • Rate limiting configuration UI")
    
    # Next steps
    print("\n🎯 RECOMMENDED NEXT STEPS")
    print("-" * 80)
    print("  1. Review each screenshot manually for visual issues")
    print("  2. Test responsive design on mobile devices")
    print("  3. Verify accessibility (keyboard nav, contrast, labels)")
    print("  4. Check form validation messages and error states")
    print("  5. Test all workflows end-to-end with fresh eyes")
    print("  6. Gather user feedback on common tasks")
    print("  7. Profile page load times and optimize slow queries")
    print("  8. Consider A/B testing for major UI changes")
    
    # Save JSON report (NO HARDCODED PATHS)
    screenshot_dir_path = os.environ.get('SCREENSHOT_DIR')
    if not screenshot_dir_path:
        repo_root = os.environ.get('REPO_ROOT')
        if not repo_root:
            raise RuntimeError("SCREENSHOT_DIR or REPO_ROOT must be set (no hardcoded paths allowed)")
        screenshot_dir_path = f"{repo_root}/screenshots"
    report_path = Path(f"{screenshot_dir_path}/ui-inspection-report.json")
    report_data = {
        "screenshots": screenshots,
        "categories": {k: [s['name'] for s in v] for k, v in categories.items()},
        "workflow_recommendations": workflow_recs,
    }
    with open(report_path, 'w') as f:
        json.dump(report_data, f, indent=2)
    print(f"\n💾 Detailed report saved to: {report_path}")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
