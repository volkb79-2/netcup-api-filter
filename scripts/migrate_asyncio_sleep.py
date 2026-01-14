#!/usr/bin/env python3
"""
Automated migration script to replace asyncio.sleep() with proper Playwright waits.

This script analyzes test files and replaces asyncio.sleep() patterns with
context-appropriate Playwright waiting mechanisms.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple


# Replacement patterns (pattern, replacement_template, explanation)
PATTERNS = [
    # Pattern 1: Sleep after click (link navigation)
    (
        r"(\s+)(await browser\.click\(['\"][^'\"]+['\"])\)\n\s+await asyncio\.sleep\([0-9.]+\)\n(\s+# .+\n)?(\s+h1 = await browser\.text\()",
        r"\1async with browser._page.expect_navigation(wait_until='domcontentloaded', timeout=5000):\n\1    \2)\n\3\4",
        "Replace click + sleep with expect_navigation"
    ),
    # Pattern 2: Sleep after goto
    (
        r"(await browser\.goto\([^)]+\))\n(\s+)await asyncio\.sleep\([0-9.]+\)",
        r"\1\n\2await browser._page.wait_for_load_state('domcontentloaded')",
        "Replace goto + sleep with wait_for_load_state"
    ),
    # Pattern 3: Sleep after button/link click without navigation expectation
    (
        r"(await [^.]+\.click\(\))\n(\s+)await asyncio\.sleep\([0-9.]+\)\n",
        r"\1\n\2await browser._page.wait_for_load_state('domcontentloaded')\n",
        "Replace click + sleep with wait_for_load_state"
    ),
    # Pattern 4: Simple sleep with no clear trigger
    (
        r"(\s+)await asyncio\.sleep\(0\.[23]\)",
        r"\1await browser._page.wait_for_timeout(100)  # Brief wait for Alpine.js/DOM updates",
        "Replace short sleep with explicit timeout note"
    ),
]


def migrate_file(filepath: Path) -> Tuple[int, List[str]]:
    """
    Migrate a single file, replacing asyncio.sleep patterns.
    
    Returns:
        Tuple of (replacement_count, changes_list)
    """
    content = filepath.read_text()
    original_content = content
    changes = []
    replacement_count = 0
    
    for pattern, replacement, explanation in PATTERNS:
        matches = list(re.finditer(pattern, content))
        if matches:
            content = re.sub(pattern, replacement, content)
            count = len(matches)
            replacement_count += count
            changes.append(f"  - {explanation}: {count} replacements")
    
    # Check if asyncio import is still needed
    if "asyncio.sleep" not in content and "import asyncio" in content:
        # Remove asyncio import if it's only on its own line
        content = re.sub(r"^import asyncio\n", "", content, flags=re.MULTILINE)
        changes.append("  - Removed unused asyncio import")
    
    # Write changes if any
    if content != original_content:
        filepath.write_text(content)
        return replacement_count, changes
    
    return 0, []


def main():
    """Main migration script."""
    test_dir = Path(__file__).parent.parent / "ui_tests" / "tests"
    
    files_to_migrate = [
        "test_user_journeys.py",
        "test_holistic_coverage.py",
        "test_email_notifications.py",
        "test_ui_functional.py",
    ]
    
    total_replacements = 0
    
    print("🔄 Starting asyncio.sleep() migration...")
    print()
    
    for filename in files_to_migrate:
        filepath = test_dir / filename
        if not filepath.exists():
            print(f"⚠️  {filename}: NOT FOUND")
            continue
        
        count, changes = migrate_file(filepath)
        
        if count > 0:
            print(f"✅ {filename}: {count} replacements")
            for change in changes:
                print(change)
            print()
            total_replacements += count
        else:
            print(f"ℹ️  {filename}: No changes needed")
    
    print()
    print(f"🎉 Migration complete: {total_replacements} total replacements across {len(files_to_migrate)} files")
    print()
    print("Next steps:")
    print("1. Review changes: git diff ui_tests/tests/")
    print("2. Run tests: pytest ui_tests/tests/ -v")
    print("3. Commit if tests pass: git add ui_tests/tests/ && git commit -m 'Migrate asyncio.sleep to Playwright waits'")


if __name__ == "__main__":
    main()
