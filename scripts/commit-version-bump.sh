#!/usr/bin/env bash
set -euo pipefail
VERSION="${1:?Usage: commit-version-bump.sh <version>}"
git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
git add custom_components/signal_lights/manifest.json
if git diff --cached --quiet; then
  echo "Version already up to date, skipping commit"
else
  git commit -m "Bump version to ${VERSION} [skip ci]"
  git push origin main
fi
