#!/usr/bin/env bash
# Extract changelog section for a given version.
# Usage: bash scripts/extract-changelog.sh <version>
set -euo pipefail
VERSION="${1:?Usage: extract-changelog.sh <version>}"
awk "/^## \[${VERSION}\]/,/^## \[/{if(/^## \[${VERSION}\]/)found=1; else if(/^## \[/ && found)exit; if(found)print}" CHANGELOG.md
