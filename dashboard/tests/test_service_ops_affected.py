import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from service_ops import preview_key_rotation
from service_ops.affected import affected_services
from service_ops.preview_key_rotation import PreviewKeyRotationDeps, RotationPreview


def _docker(name, status="exited", registered=False):
    return {"name": name, "status": status, "openwebui_registered": registered}


def test_only_services_in_the_db_are_affected_and_every_list_is_sorted():
    state = affected_services(
        ["b", "a", "c"],
        [_docker("c", "running"), _docker("open-webui", "running", True), _docker("a", "running", True), _docker("b")],
    )

    assert state == (["a", "b", "c"], ["a", "c"], ["a"])


def test_a_db_service_without_a_container_still_counts_toward_the_total():
    assert affected_services(["a", "ghost"], [_docker("a")]) == (["a", "ghost"], [], [])


def test_a_missing_flag_reads_as_false():
    assert affected_services(["a"], [{"name": "a"}]) == (["a"], [], [])


def test_the_preview_counts_and_owns_its_wire_body():
    preview = preview_key_rotation(PreviewKeyRotationDeps(lambda: (["a", "b"], ["a"], ["b"])))

    assert preview == RotationPreview(2, ["a"], ["b"])
    assert preview.body() == {"total_services": 2, "running": ["a"], "openwebui_registered": ["b"]}
