import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config


def test_failed_init_does_not_poison_later_calls(tmp_path):
    """A failed init_config (missing token) must not permanently disable
    re-validation and logging setup: once the token exists, the next call
    succeeds and installs the handlers. The flag must stay False across the
    failure — this is what #191's fix pins."""
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
        assert handlers_after.count("FileHandler") > handlers_before.count("FileHandler")
        assert handlers_after.count("StreamHandler") > handlers_before.count("StreamHandler")
    finally:
        config.DASHBOARD_TOKEN = saved_token
        config._config_initialized = saved_flag
        os.chdir(saved_cwd)
