import json
import os
import sys
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compose_manager import ComposeManager

TEST_TOKEN = "test-token"


@pytest.fixture(autouse=True)
def set_env_vars():
    os.environ["DASHBOARD_TOKEN"] = TEST_TOKEN


@pytest.fixture
def compose_manager(tmp_path):
    """Provide a ComposeManager backed by temp files instead of the project's real compose files."""
    compose_path = tmp_path / "docker-compose.yml"
    compose_path.write_text(
        "services:\n"
        "  # <<<<<<< BEGIN DYNAMIC\n"
        "  test-svc:\n"
        "    image: test\n"
        "  # >>>>>>> END DYNAMIC\n"
        "\n"
        "networks:\n"
        "  llm-network:\n"
        "    driver: bridge\n"
    )
    services_path = tmp_path / "services.json"
    services_path.write_text(
        json.dumps(
            {
                "test-svc": {
                    "template_type": "llamacpp",
                    "alias": "test",
                    "port": 3301,
                    "model_path": "/models/test.gguf",
                    "api_key": "test-key",
                    "params": {},
                }
            }
        )
    )
    return ComposeManager(str(compose_path), services_db_file=str(services_path))


class TestRemoveServiceUsesValidation:
    """Prove remove_service validates the compose file — unlike current behavior."""

    @patch.object(ComposeManager, "_validate_compose_file")
    def test_remove_service_calls_validate(self, mock_validate, compose_manager):
        """remove_service should call _validate_compose_file before writing.

        _atomic_add_service and _rebuild_compose_file_locked both call
        _validate_compose_file on a temp file before replacing the real one.
        remove_service does not — it writes directly to compose_path.
        """
        compose_manager.remove_service("test-svc")
        mock_validate.assert_called_once()

    @patch("os.replace")
    @patch.object(ComposeManager, "_validate_compose_file")
    def test_remove_service_uses_temp_file_before_replace(
        self, mock_validate, mock_replace, compose_manager
    ):
        """remove_service should write to a temp file and then os.replace,
        not write directly to compose_path.
        """
        compose_manager.remove_service("test-svc")
        # os.replace should be called once (temp -> final path)
        mock_replace.assert_called_once()


class TestAddServiceUsesValidation:
    """Confirm _atomic_add_service does use validation as a baseline."""

    @patch("os.replace")
    @patch.object(ComposeManager, "_validate_compose_file")
    def test_add_service_calls_validate(
        self, mock_validate, mock_replace, compose_manager
    ):
        mock_validate.return_value = {"valid": True, "error": None}

        config = compose_manager._load_services_db()
        if "new-svc" in config:
            pytest.skip("Service name collision")

        try:
            compose_manager.add_service(
                "new-svc",
                {
                    "template_type": "llamacpp",
                    "alias": "new",
                    "port": 3390,
                    "model_path": "/models/new.gguf",
                    "api_key": "k",
                    "params": {},
                },
            )
            mock_validate.assert_called_once()
        finally:
            config = compose_manager._load_services_db()
            config.pop("new-svc", None)
            compose_manager._save_services_db(config)
