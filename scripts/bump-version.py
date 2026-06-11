#!/usr/bin/env python3
"""Bump the version in manifest.json.

Usage: python scripts/bump-version.py <version>

Accepts X.Y.Z release versions and X.Y.Z{a|b|rc}N pre-release versions
(PEP 440 style, e.g. 1.3.0b1) — the same format the release workflow
derives from git tags.
"""
import json
import re
import sys
from pathlib import Path

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+((a|b|rc)\d+)?$")

if len(sys.argv) < 2:
    print("Usage: python scripts/bump-version.py <version>", file=sys.stderr)
    sys.exit(1)

version = sys.argv[1]
if not VERSION_RE.match(version):
    print(
        f"Invalid version '{version}' — expected X.Y.Z or X.Y.Z{{a|b|rc}}N "
        "(e.g. 1.3.0 or 1.3.0b1)",
        file=sys.stderr,
    )
    sys.exit(1)

manifest = Path("custom_components/signal_lights/manifest.json")
data = json.loads(manifest.read_text())
data["version"] = version
manifest.write_text(json.dumps(data, indent=2) + "\n")
print(f"Bumped manifest.json to {version}")
