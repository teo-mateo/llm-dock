import json
import os
import sys
from unittest.mock import patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compose_manager import ComposeManager, _SERVICE_NAME_ERROR, _valid_service_name

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


class TestRebuildKeepsRestartFlag:
    def test_restart_no_survives_a_rebuild(self, compose_manager):
        """Every engine template emits `restart: no`; YAML 1.1 reads that as False, so a
        round-trip writes `restart: false` and `docker compose config` then rejects the
        whole file. Only the marker-delimited text path may rewrite it.
        """
        with patch.object(
            ComposeManager,
            "_validate_compose_file",
            return_value={"valid": True, "error": None},
        ):
            compose_manager.rebuild_compose_file()

        written = compose_manager.compose_path.read_text()
        assert "restart: no" in written
        assert "restart: false" not in written


class TestRebuildValidatesBeforePromoting:
    def test_generated_file_rejected_by_docker_is_never_promoted(self, compose_manager):
        """The temp file is validated before os.replace, so a rejected render leaves the
        live compose file untouched rather than swapped for an unusable one — every
        later service write, and every container start, reads that file.
        """
        before = compose_manager.compose_path.read_text()
        with patch.object(
            ComposeManager,
            "_validate_compose_file",
            return_value={"valid": False, "error": "boom"},
        ):
            with pytest.raises(ValueError):
                compose_manager.rebuild_compose_file()

        assert compose_manager.compose_path.read_text() == before
        assert not compose_manager.compose_path.with_suffix(".yml.tmp").exists()


class TestTabbyapiRender:
    """Cover the tabbyapi (EXL3) template rendering path."""

    def _render(self, mgr, monkeypatch, tmp_path, params):
        monkeypatch.setenv("LLM_DOCK_TABBY_KEYS_DIR", str(tmp_path / "keys"))
        cfg = {
            "template_type": "tabbyapi",
            "alias": "laguna",
            "port": 3328,
            "model_path": "/hf-cache/hub/models--turboderp--X-exl3/snapshots/abc123",
            "api_key": "llmd-abc",
            "params": params,
        }
        return mgr._render_service("exl3-laguna", cfg)

    def test_model_dir_and_name_are_split(self, compose_manager, monkeypatch, tmp_path):
        out = self._render(compose_manager, monkeypatch, tmp_path, {})
        assert "--model-dir /hf-cache/hub/models--turboderp--X-exl3/snapshots" in out
        assert "--model-name abc123" in out

    def test_bind_mount_honors_keys_dir_override(
        self, compose_manager, monkeypatch, tmp_path
    ):
        """The api_tokens.yml bind source must follow LLM_DOCK_TABBY_KEYS_DIR."""
        out = self._render(compose_manager, monkeypatch, tmp_path, {})
        expected = f"{tmp_path / 'keys' / 'exl3-laguna.yml'}:/app/api_tokens.yml:ro"
        assert expected in out
        assert (tmp_path / "keys" / "exl3-laguna.yml").is_file()

    def test_empty_bool_params_render_with_a_value(
        self, compose_manager, monkeypatch, tmp_path
    ):
        """TabbyAPI booleans take a value; an empty value must not render bare."""
        out = self._render(
            compose_manager, monkeypatch, tmp_path, {"--vision": "", "--max-seq-len": "32768"}
        )
        assert "--vision True" in out
        assert "--vision\n" not in out
        assert "--max-seq-len 32768" in out


class TestVllmRender:
    """Cover optional vLLM runtime-overlay mounts."""

    def test_extra_volumes_render(self, compose_manager):
        cfg = {
            "template_type": "vllm",
            "alias": "qwen",
            "port": 3301,
            "model_name": "org/model",
            "api_key": "test-key",
            "params": {},
            "volumes": [
                "${HOME}/overlay.py:/usr/local/lib/python3.12/site-packages/pkg/module.py:ro",
                "${HOME}/ple-cache:/ple-cache:ro",
            ],
        }

        out = compose_manager._render_service("vllm-qwen", cfg)

        assert cfg["volumes"][0] in out
        assert cfg["volumes"][1] in out


class TestDottedServiceNames:
    """Existing dotted names (e.g. 'llamacpp-glm-5.3-flash-q2kxl') must be renameable."""

    def test_valid_service_name_accepts_dots(self):
        assert _valid_service_name("llamacpp-glm-5.3-flash-q2kxl") is True

    def test_valid_service_name_rejects_other_characters(self):
        assert _valid_service_name("llamacpp-glm/5") is False
        assert "hyphens" in _SERVICE_NAME_ERROR

    @pytest.mark.parametrize(
        "name",
        [".llamacpp-glm-5.3", "-llamacpp-glm-5.3", "_llamacpp-glm-5.3", "服务"],
    )
    def test_valid_service_name_rejects_names_docker_rejects(self, name):
        assert _valid_service_name(name) is False
        assert "start with a letter or digit" in _SERVICE_NAME_ERROR

    @patch.object(ComposeManager, "rebuild_compose_file")
    def test_rename_to_dotted_name(self, mock_rebuild, compose_manager):
        compose_manager.rename_service("test-svc", "test-svc-5.3-flash-lru")

        services = compose_manager._load_services_db()
        assert "test-svc-5.3-flash-lru" in services
        assert "test-svc" not in services
