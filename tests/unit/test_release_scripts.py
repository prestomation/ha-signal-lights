"""Unit tests for the release helper scripts (scripts/bump-version.py,
scripts/extract-changelog.sh).

Pure subprocess tests — no Home Assistant dependencies. These cover the
beta/pre-release version handling used by the release workflow.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
BUMP_SCRIPT = REPO_ROOT / "scripts" / "bump-version.py"
CHANGELOG_SCRIPT = REPO_ROOT / "scripts" / "extract-changelog.sh"

SAMPLE_CHANGELOG = """\
# Changelog

## [Unreleased]

### Fixed
- Unreleased fix line

## [1.2.0] - 2026-04-02

### Added
- Cycling feature

## [1.0.0] - 2026-03-20

### Added
- Initial release
"""


@pytest.fixture
def workdir(tmp_path):
    """A temp working dir with a manifest and changelog fixture."""
    manifest_dir = tmp_path / "custom_components" / "signal_lights"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "manifest.json").write_text(
        json.dumps({"domain": "signal_lights", "version": "1.2.0"}, indent=2) + "\n"
    )
    (tmp_path / "CHANGELOG.md").write_text(SAMPLE_CHANGELOG)
    return tmp_path


def run_bump(workdir, version):
    return subprocess.run(
        [sys.executable, str(BUMP_SCRIPT), version],
        cwd=workdir, capture_output=True, text=True,
    )


def run_extract(workdir, version):
    return subprocess.run(
        ["bash", str(CHANGELOG_SCRIPT), version],
        cwd=workdir, capture_output=True, text=True,
    )


def manifest_version(workdir):
    manifest = workdir / "custom_components" / "signal_lights" / "manifest.json"
    return json.loads(manifest.read_text())["version"]


class TestBumpVersion:
    def test_bumps_release_version(self, workdir):
        result = run_bump(workdir, "1.3.0")
        assert result.returncode == 0, result.stderr
        assert manifest_version(workdir) == "1.3.0"

    @pytest.mark.parametrize("version", ["1.3.0b1", "1.3.0rc2", "2.0.0a1"])
    def test_accepts_prerelease_versions(self, workdir, version):
        result = run_bump(workdir, version)
        assert result.returncode == 0, result.stderr
        assert manifest_version(workdir) == version

    @pytest.mark.parametrize("version", [
        "not-a-version",
        "1.3",
        "v1.3.0",          # tag prefix must be stripped by the workflow
        "1.3.0-beta.1",    # semver-style suffix — PEP 440 style only
        "1.3.0b",          # missing pre-release number
        "1.3.0 && rm -rf", # garbage
    ])
    def test_rejects_invalid_versions(self, workdir, version):
        result = run_bump(workdir, version)
        assert result.returncode != 0, (
            f"bump-version.py accepted invalid version {version!r}"
        )
        assert manifest_version(workdir) == "1.2.0", "manifest must be untouched"


class TestExtractChangelog:
    def test_extracts_exact_version_section(self, workdir):
        result = run_extract(workdir, "1.2.0")
        assert result.returncode == 0, result.stderr
        assert "Cycling feature" in result.stdout
        assert "Initial release" not in result.stdout
        assert "Unreleased fix line" not in result.stdout

    def test_section_header_is_not_included(self, workdir):
        """The release title already names the version — notes carry only
        the section body."""
        result = run_extract(workdir, "1.2.0")
        assert "## [1.2.0]" not in result.stdout

    def test_extracts_oldest_section_without_trailing_sections(self, workdir):
        result = run_extract(workdir, "1.0.0")
        assert "Initial release" in result.stdout
        assert "Cycling feature" not in result.stdout

    def test_prerelease_falls_back_to_base_version_section(self, workdir):
        """v1.2.0b1 has no own section — use the [1.2.0] section."""
        result = run_extract(workdir, "1.2.0b1")
        assert result.returncode == 0, result.stderr
        assert "Cycling feature" in result.stdout

    def test_prerelease_falls_back_to_unreleased_section(self, workdir):
        """A beta cut before the final section exists uses [Unreleased]."""
        result = run_extract(workdir, "1.3.0b1")
        assert result.returncode == 0, result.stderr
        assert "Unreleased fix line" in result.stdout
        # The "[Unreleased]" heading must not leak into published notes
        assert "Unreleased]" not in result.stdout

    def test_unknown_release_version_yields_empty_output(self, workdir):
        """Final releases never fall back — the workflow's generic text kicks in."""
        result = run_extract(workdir, "9.9.9")
        assert result.stdout.strip() == ""
