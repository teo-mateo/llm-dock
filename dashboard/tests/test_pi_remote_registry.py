from pi_remote.contract import STALE_AFTER_MS
from pi_remote.frames import ByeFrame, HeartbeatFrame, HelloFrame
from pi_remote.registry import PresenceRegistry, RegistryResult


def hello(instance_id="i1", session_id="s1"):
    return HelloFrame(
        session_id=session_id,
        instance_id=instance_id,
        session_file=None,
        cwd="/tmp",
        name=None,
        pid=1,
        model=None,
        thinking_level=None,
        reason="startup",
        previous_session_id=None,
        pi_version=None,
        ext_version="0.1.0",
    )


def heartbeat(state="idle", context=None, sent_at=0):
    return HeartbeatFrame(
        session_id="s1",
        instance_id="i1",
        state=state,
        context=context,
        sent_at=sent_at,
    )


def bye(reason="shutdown"):
    return ByeFrame(session_id="s1", instance_id="i1", reason=reason)


def test_same_session_two_instances_coexist():
    registry = PresenceRegistry()
    registry.register(hello("i1"), 1000)
    registry.register(hello("i2"), 1000)
    assert len(registry.entries(1000)) == 2
    assert registry.get("s1", "i1", 1000) is not None
    assert registry.get("s1", "i2", 1000) is not None


def test_heartbeat_updates_last_seen():
    registry = PresenceRegistry()
    registry.register(hello(), 1000)
    assert registry.heartbeat(heartbeat(), 5000) == RegistryResult.OK
    assert registry.get("s1", "i1", 5000).last_seen == 5000


def test_45_seconds_is_the_stale_boundary():
    registry = PresenceRegistry()
    registry.register(hello(), 1000)
    assert registry.heartbeat(heartbeat(), 1000 + STALE_AFTER_MS) == RegistryResult.OK
    registry.register(hello("i2", "s2"), 1000)
    frame = HeartbeatFrame("s2", "i2", "idle", None, 0)
    assert registry.heartbeat(frame, 1000 + STALE_AFTER_MS + 1) == RegistryResult.STALE


def test_stale_entry_is_hidden_and_expired():
    registry = PresenceRegistry()
    registry.register(hello(), 1000)
    late = 1000 + STALE_AFTER_MS + 1
    assert registry.get("s1", "i1", late) is None
    assert registry.entries(late) == []
    assert registry.expire(late) == [("s1", "i1")]
    assert registry.entries(late) == []


def test_unknown_instance_heartbeat_and_bye():
    registry = PresenceRegistry()
    assert registry.heartbeat(heartbeat(), 1000) == RegistryResult.UNKNOWN
    assert registry.bye(bye(), 1000) == RegistryResult.UNKNOWN


def test_bye_removes_the_instance():
    registry = PresenceRegistry()
    registry.register(hello(), 1000)
    assert registry.bye(bye(), 1000) == RegistryResult.OK
    assert registry.get("s1", "i1", 1000) is None


def test_stale_bye_returns_stale_without_removing():
    registry = PresenceRegistry()
    registry.register(hello(), 1000)
    late = 1000 + STALE_AFTER_MS + 1
    assert registry.bye(bye(), late) == RegistryResult.STALE
    assert registry.get("s1", "i1", late) is None
    assert registry.expire(late) == [("s1", "i1")]
