"""
run.py
------
Cross-platform entry point for Yards & Parts Platform.
Runs out of the box on Windows, macOS, and Linux.
"""

import sys
import os
import uvicorn

if __name__ == "__main__":
    # Ensure current directory is on sys.path
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    print("\n" + "=" * 65)
    print("   YARDS & PARTS AUTOMOTIVE PLATFORM (UNIFIED 2.0)")
    print("=" * 65)
    print("  • VIN Quoting Engine:    http://localhost:8000/quoting")
    print("  • Sales Rep Cockpit:     http://localhost:8000/dashboard/rep")
    print("  • Cart Recovery Mailer:  http://localhost:8000/dashboard/auto-mailer")
    print("  • Live API Docs:         http://localhost:8000/docs")
    print("=" * 65 + "\n")

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
