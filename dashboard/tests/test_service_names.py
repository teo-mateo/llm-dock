import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from service_names import SERVICE_NAME_ERROR, validate_rename

EXISTING = {"old": {}, "taken": {}}


@pytest.mark.parametrize(
    "new_name,expected",
    [
        ("fresh", None),
        ("llamacpp-glm-5.3-flash", None),
        ("a" * 63, None),
        ("", "Service name cannot be empty"),
        ("a" * 64, "Service name too long (max 63 characters)"),
        ("bad name", SERVICE_NAME_ERROR),
        ("-leading", SERVICE_NAME_ERROR),
        ("slash/name", SERVICE_NAME_ERROR),
        ("taken", "Service 'taken' already exists"),
    ],
)
def test_validate_rename(new_name, expected):
    assert validate_rename("old", new_name, EXISTING) == expected


def test_an_unknown_old_name_is_refused():
    assert validate_rename("ghost", "fresh", EXISTING) == "Service 'ghost' not found in database"


def test_the_rules_run_in_the_order_the_compose_manager_always_applied_them():
    assert validate_rename("ghost", "bad name", EXISTING) == SERVICE_NAME_ERROR
    assert validate_rename("ghost", "taken", EXISTING) == "Service 'ghost' not found in database"


def test_the_compose_manager_enforces_the_same_rules(tmp_path):
    import json

    from compose_manager import ComposeManager

    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    (tmp_path / "services.json").write_text(json.dumps({"old": {}, "taken": {}}))
    manager = ComposeManager(str(tmp_path / "docker-compose.yml"))

    with pytest.raises(ValueError, match="already exists"):
        manager.rename_service("old", "taken")
    with pytest.raises(ValueError, match="start with a letter"):
        manager.rename_service("old", "bad name")
