#!/usr/bin/env python3
"""Bump the version in manifest.json.

Usage: python scripts/bump-version.py <version>
"""
import json
import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: python scripts/bump-version.py <version>", file=sys.stderr)
    sys.exit(1)

version = sys.argv[1]
manifest = Path("custom_components/signal_lights/manifest.json")
data = json.loads(manifest.read_text())
data["version"] = version
manifest.write_text(json.dumps(data, indent=2) + "\n")
print(f"Bumped manifest.json to {version}")
