from pi_remote.contract import STALE_AFTER_MS
from pi_remote.registry import PresenceRegistry


FIELDS = {
    "session_id": "s1",
    "instance_id": "i1",
    "session_file": None,
    "cwd": "/tmp",
    "name": None,
    "pid": 1,
    "model": None,
    "thinking_level": None,
    "reason": "startup",
    "previous_session_id": None,
    "pi_version": None,
    "ext_version": "0.1.0",
}


def test_same_session_two_instances_coexist():
    registry = PresenceRegistry()
    first = dict(FIELDS, instance_id="i1")
    second = dict(FIELDS, instance_id="i2")
    registry.register(first, 1000)
    registry.register(second, 1000)
    assert len(registry.entries()) == 2
    assert registry.get("s1", "i1") is not None
    assert registry.get("s1", "i2") is not None


def test_heartbeat_updates_last_seen():
    registry = PresenceRegistry()
    registry.register(FIELDS, 1000)
    assert registry.heartbeat("s1", "i1", "idle", None, 5000, 5000) == "ok"
    assert registry.get("s1", "i1").last_seen == 5000


def test_45_seconds_is_the_stale_boundary():
    registry = PresenceRegistry()
    registry.register(FIELDS, 1000)
    assert registry.heartbeat("s1", "i1", "idle", None, 0, 1000 + STALE_AFTER_MS) == "ok"
    other = dict(FIELDS, session_id="s2", instance_id="i2")
    registry.register(other, 1000)
    assert registry.heartbeat("s2", "i2", "idle", None, 0, 1000 + STALE_AFTER_MS + 1) == "stale"
    assert registry.get("s2", "i2") is None


def test_unknown_instance_heartbeat_and_bye():
    registry = PresenceRegistry()
    assert registry.heartbeat("s1", "i1", "idle", None, 0, 1000) == "unknown"
    assert registry.bye("s1", "i1", 1000) == "unknown"


def test_bye_removes_the_instance():
    registry = PresenceRegistry()
    registry.register(FIELDS, 1000)
    assert registry.bye("s1", "i1", 1000) == "ok"
    assert registry.get("s1", "i1") is None


def test_stale_bye():
    registry = PresenceRegistry()
    registry.register(FIELDS, 1000)
    assert registry.bye("s1", "i1", 1000 + STALE_AFTER_MS + 1) == "stale"
    assert registry.get("s1", "i1") is None
