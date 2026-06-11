#!/usr/bin/env bash
# Extract the CHANGELOG.md section for a given version.
#
# Usage: bash scripts/extract-changelog.sh <version>
#
# Lookup order:
#   1. The exact section: "## [<version>]"
#   2. For pre-release versions (e.g. 1.3.0b1, 1.3.0rc2): the base version
#      section "## [1.3.0]", then "## [Unreleased]" — betas are usually cut
#      before the final section exists.
# Prints nothing when no section is found (the release workflow falls back
# to a generic note).
set -euo pipefail
VERSION="${1:?Usage: extract-changelog.sh <version>}"

extract() {
  # Emits the section body only — the header line is skipped because the
  # GitHub release title already names the version (and beta fallbacks
  # would otherwise leak an "## [Unreleased]" heading into release notes).
  awk -v ver="$1" '
    /^## \[/ {
      if (found) exit
      if (index($0, "## [" ver "]") == 1) { found = 1; next }
    }
    found { print }
  ' CHANGELOG.md
}

OUTPUT=$(extract "$VERSION")

if [ -z "$OUTPUT" ]; then
  BASE=$(printf '%s' "$VERSION" | sed -E 's/(a|b|rc)[0-9]+$//')
  if [ "$BASE" != "$VERSION" ]; then
    OUTPUT=$(extract "$BASE")
    if [ -z "$OUTPUT" ]; then
      OUTPUT=$(extract "Unreleased")
    fi
  fi
fi

printf '%s\n' "$OUTPUT"
