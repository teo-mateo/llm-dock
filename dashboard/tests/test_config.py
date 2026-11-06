import logging
import logging.handlers
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config


def test_failed_init_does_not_poison_later_calls(tmp_path):
    """A failed init_config (missing token) must not permanently disable
    re-validation and logging setup: once the token exists, the next call
    succeeds and installs the handlers. The flag must stay False across the
    failure — that is what this pins."""
    saved_token = config.DASHBOARD_TOKEN
    saved_flag = config._config_initialized
    saved_cwd = os.getcwd()
    try:
        config.DASHBOARD_TOKEN = None
        config._config_initialized = False

        with pytest.raises(ValueError):
            config.init_config()
        assert config._config_initialized is False

        config.DASHBOARD_TOKEN = "test-token-config"
        os.chdir(tmp_path)
        root = logging.getLogger()
        handlers_before = [type(h).__name__ for h in root.handlers]

        config.init_config()

        # The successful call must have installed a file and a console
        # handler. Count-based, not presence-based: earlier apps in the
        # suite's process already carry handlers, so presence alone would
        # pass even if this call were a no-op — which is exactly the
        # regression this test guards.
        handlers_after = [type(h).__name__ for h in root.handlers]
        assert handlers_after.count("RotatingFileHandler") > handlers_before.count("RotatingFileHandler")
        assert handlers_after.count("StreamHandler") > handlers_before.count("StreamHandler")
    finally:
        config.DASHBOARD_TOKEN = saved_token
        config._config_initialized = saved_flag
        os.chdir(saved_cwd)


def _access_record(code):
    return logging.LogRecord(
        "werkzeug", logging.INFO, __file__, 0,
        '127.0.0.1 - - [06/Nov/2026 10:00:00] "%s" %s %s\n',
        ("GET /api/services/x/image HTTP/1.1", code, "-"), None,
    )


@pytest.mark.parametrize("code,kept", [("200", False), ("304", False), ("101", False),
                                       ("401", True), ("404", True), ("500", True)])
def test_access_filter_drops_successful_requests_only(code, kept):
    assert config.QuietAccessFilter().filter(_access_record(code)) is kept


def test_access_filter_keeps_non_access_werkzeug_records():
    record = logging.LogRecord("werkzeug", logging.INFO, __file__, 0,
                               "Running on %s %s %s", ("http://0.0.0.0:3399", "200", "x"), None)
    assert config.QuietAccessFilter().filter(record) is True


def test_init_config_rotates_at_the_configured_path(tmp_path, monkeypatch):
    log_file = tmp_path / "sub-dashboard.log"
    monkeypatch.setenv("DASHBOARD_LOG_FILE", str(log_file))
    monkeypatch.setenv("DASHBOARD_LOG_MAX_BYTES", "1234")
    monkeypatch.setenv("DASHBOARD_LOG_BACKUPS", "2")
    monkeypatch.setattr(config, "_config_initialized", False)
    monkeypatch.setattr(config, "DASHBOARD_TOKEN", "test-token-config")
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        config.init_config()
        added = [h for h in root.handlers if h not in before]
        rotating = [h for h in added if isinstance(h, logging.handlers.RotatingFileHandler)]
        assert len(rotating) == 1
        assert rotating[0].baseFilename == str(log_file)
        assert rotating[0].maxBytes == 1234
        assert rotating[0].backupCount == 2
        werkzeug_filters = logging.getLogger("werkzeug").filters
        assert sum(isinstance(f, config.QuietAccessFilter) for f in werkzeug_filters) == 1
    finally:
        for h in root.handlers[:]:
            if h not in before:
                root.removeHandler(h)
                h.close()


def test_default_log_file_is_anchored_next_to_config():
    assert config.DEFAULT_LOG_FILE == os.path.join(os.path.dirname(os.path.abspath(config.__file__)), "dashboard.log")
