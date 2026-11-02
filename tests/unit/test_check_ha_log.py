"""Unit tests for scripts/check_ha_log.py.

Run with: python -m pytest tests/unit/test_check_ha_log.py -v
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[2] / "scripts" / "check_ha_log.py"
_spec = importlib.util.spec_from_file_location("check_ha_log", SCRIPT)
check_ha_log = importlib.util.module_from_spec(_spec)
sys.modules["check_ha_log"] = check_ha_log
_spec.loader.exec_module(check_ha_log)

TS = "2026-11-02 10:00:00.123"

CLEAN_LOG = f"""\
{TS} INFO (MainThread) [homeassistant.core] Starting Home Assistant
{TS} WARNING (SyncWorker_0) [homeassistant.loader] We found a custom integration signal_lights which has not been tested by Home Assistant. This component might cause stability problems, be sure to disable it if you experience issues with Home Assistant
{TS} DEBUG (MainThread) [custom_components.signal_lights.coordinator] debug line is fine
{TS} INFO (MainThread) [custom_components.signal_lights] Setup done
{TS} WARNING (MainThread) [homeassistant.components.foo] Other integration warning
"""

BLOCKING_LOG = f"""\
{TS} INFO (MainThread) [homeassistant.core] Starting Home Assistant
{TS} WARNING (MainThread) [homeassistant.util.loop] Detected blocking call to read_text with args (PosixPath('/config/custom_components/signal_lights/manifest.json'),) inside the event loop by custom integration 'signal_lights' at custom_components/signal_lights/diagnostics.py, line 33: manifest_data = json.loads(manifest_path.read_text(encoding="utf-8")) (offender: /usr/local/lib/python3.13/pathlib/_local.py, line 546: return f.read()), please create a bug report at https://github.com/prestomation/ha-signal-lights/issues
Traceback (most recent call last):
  File "/config/custom_components/signal_lights/diagnostics.py", line 33, in async_get_config_entry_diagnostics
"""


def run(log: str, domain: str = "signal_lights", allowlist=None):
    records = check_ha_log.parse_records(log.splitlines())
    return check_ha_log.check_records(records, domain, allowlist or [])


def test_clean_log_has_no_findings():
    assert run(CLEAN_LOG) == []


def test_generic_custom_integration_notice_is_ignored():
    log = (
        f"{TS} WARNING (SyncWorker_0) [homeassistant.loader] We found a custom "
        "integration signal_lights which has not been tested by Home Assistant. "
        "This component might cause stability problems\n"
    )
    assert run(log) == []


@pytest.mark.parametrize("level", ["WARNING", "ERROR", "CRITICAL"])
def test_integration_logger_at_warning_or_higher_fails(level):
    log = f"{TS} {level} (MainThread) [custom_components.signal_lights.engine] boom\n"
    findings = run(log)
    assert len(findings) == 1
    assert "custom_components.signal_lights.engine" in findings[0].rule


def test_integration_root_logger_fails():
    log = f"{TS} ERROR (MainThread) [custom_components.signal_lights] boom\n"
    assert len(run(log)) == 1


def test_logger_of_other_domain_is_not_ours():
    log = f"{TS} ERROR (MainThread) [custom_components.signal_lights_extra] boom\n"
    assert run(log) == []
    log = f"{TS} ERROR (MainThread) [custom_components.other] boom\n"
    assert run(log) == []


def test_blocking_call_for_our_domain_fails():
    findings = run(BLOCKING_LOG)
    assert len(findings) == 1
    assert "blocking call" in findings[0].rule
    assert "diagnostics.py, line 33" in findings[0].text


def test_blocking_call_for_other_domain_is_ignored():
    log = (
        f"{TS} WARNING (MainThread) [homeassistant.util.loop] Detected blocking "
        "call to open inside the event loop by custom integration 'other' at "
        "custom_components/other/x.py, line 1\n"
    )
    assert run(log) == []


def test_docker_compose_prefix_is_accepted():
    log = "homeassistant-1  | " + BLOCKING_LOG.splitlines()[1] + "\n"
    assert len(run(log)) == 1


@pytest.mark.parametrize(
    "message",
    [
        "/config/custom_components/signal_lights/engine.py:10: RuntimeWarning: "
        "coroutine 'foo' was never awaited",
        "Task exception was never retrieved\nTraceback (most recent call last):\n"
        '  File "/config/custom_components/signal_lights/coordinator.py", line 5',
        "Executing <Task pending name='Task-9' coro=<run() running at "
        "/config/custom_components/signal_lights/coordinator.py:55>> took 0.350 seconds",
        "Unclosed client session client_session: <aiohttp.ClientSession> created "
        "at /config/custom_components/signal_lights/x.py:3",
        "The integration 'signal_lights' uses a deprecated call "
        "(custom_components/signal_lights/__init__.py)",
    ],
)
def test_known_bad_patterns_for_our_domain_fail(message):
    log = f"{TS} WARNING (MainThread) [asyncio] {message}\n"
    assert len(run(log)) == 1


def test_known_bad_patterns_for_other_code_are_ignored():
    log = (
        f"{TS} WARNING (MainThread) [asyncio] Executing <Task pending name='T' "
        "coro=<run() running at /usr/src/homeassistant/foo.py:5>> took 0.4 seconds\n"
        f"{TS} WARNING (MainThread) [py.warnings] /config/custom_components/other/a.py:1: "
        "RuntimeWarning: coroutine 'x' was never awaited\n"
    )
    assert run(log) == []


def test_traceback_lines_belong_to_the_record_before_them():
    log = (
        f"{TS} ERROR (MainThread) [asyncio] Task exception was never retrieved\n"
        "future: <Task finished>\n"
        "Traceback (most recent call last):\n"
        '  File "/config/custom_components/signal_lights/engine.py", line 1, in f\n'
        f"{TS} INFO (MainThread) [homeassistant.core] later line\n"
    )
    findings = run(log)
    assert len(findings) == 1
    assert findings[0].line_no == 1


def test_allowlist_entry_hides_a_finding(tmp_path):
    path = tmp_path / "allow.txt"
    path.write_text(
        "# The test setup has no real light, so this warning is expected.\n"
        "light\\.missing is unavailable\n"
    )
    allow = check_ha_log.load_allowlist(path)
    log = (
        f"{TS} WARNING (MainThread) [custom_components.signal_lights.engine] "
        "light.missing is unavailable\n"
        f"{TS} WARNING (MainThread) [custom_components.signal_lights.engine] other\n"
    )
    findings = run(log, allowlist=allow)
    assert len(findings) == 1
    assert "other" in findings[0].text


def test_allowlist_entry_without_reason_is_rejected(tmp_path):
    path = tmp_path / "allow.txt"
    path.write_text("light\\.missing is unavailable\n")
    with pytest.raises(ValueError, match="no reason"):
        check_ha_log.load_allowlist(path)


def test_allowlist_reason_does_not_carry_over_a_blank_line(tmp_path):
    path = tmp_path / "allow.txt"
    path.write_text("# Reason one.\nfirst\n\nsecond\n")
    with pytest.raises(ValueError, match="no reason"):
        check_ha_log.load_allowlist(path)


def test_shipped_allowlist_is_valid():
    check_ha_log.load_allowlist(SCRIPT.with_name("ha_log_allowlist.txt"))


def _cli(tmp_path, log_text, *extra):
    log = tmp_path / "ha.log"
    log.write_text(log_text)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--domain", "signal_lights", *extra, str(log)],
        capture_output=True,
        text=True,
    )


def test_cli_exit_codes(tmp_path):
    assert _cli(tmp_path, CLEAN_LOG).returncode == 0
    failed = _cli(tmp_path, BLOCKING_LOG)
    assert failed.returncode == 1
    assert "diagnostics.py" in failed.stdout
    # An empty log must not pass.
    assert _cli(tmp_path, "").returncode == 2
    assert _cli(tmp_path, "no ha records here\n").returncode == 2


def test_cli_reads_stdin():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--domain", "signal_lights"],
        input=BLOCKING_LOG,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1


def test_cli_bad_allowlist_exits_2(tmp_path):
    allow = tmp_path / "allow.txt"
    allow.write_text("no reason here\n")
    assert _cli(tmp_path, CLEAN_LOG, "--allowlist", str(allow)).returncode == 2
