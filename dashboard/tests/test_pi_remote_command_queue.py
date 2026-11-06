import itertools
import re
import threading
import time

from pi_remote.command_queue import CommandQueue
from pi_remote.commands import CommandResult


def counting_ids():
    counter = itertools.count(1)
    return lambda: f"cmd-{next(counter)}"


KEY = ("s1", "i1")


def _thread(target):
    thread = threading.Thread(target=target)
    thread.start()
    return thread


def test_take_returns_new_commands_once():
    queue = CommandQueue(new_id=counting_ids())
    queue.enqueue(KEY, "abort", {}, 1000)
    assert [command.command_id for command in queue.take(KEY, 1000, 0)] == ["cmd-1"]
    assert queue.take(KEY, 1000, 0) == []


def test_redelivers_after_timeout_without_result():
    queue = CommandQueue(redeliver_after_ms=30000, new_id=counting_ids())
    queue.enqueue(KEY, "abort", {}, 1000)
    assert [command.command_id for command in queue.take(KEY, 1000, 0)] == ["cmd-1"]
    assert queue.take(KEY, 30000, 0) == []
    assert [command.command_id for command in queue.take(KEY, 31000, 0)] == ["cmd-1"]


def test_complete_removes_and_returns_known_results():
    queue = CommandQueue(new_id=counting_ids())
    queue.enqueue(KEY, "abort", {}, 1000)
    queue.take(KEY, 1000, 0)
    result = CommandResult("cmd-1", True, None)
    assert queue.complete(KEY, [result]) == [result]
    assert queue.take(KEY, 31000, 0) == []
    assert queue.wait_result("cmd-1", 0) == result


def test_wait_result_returns_when_completed():
    queue = CommandQueue(new_id=counting_ids())
    queue.enqueue(KEY, "abort", {}, 1000)
    box = {}

    def complete():
        time.sleep(0.05)
        box["result"] = queue.complete(KEY, [CommandResult("cmd-1", True, None)])

    thread = _thread(complete)
    result = queue.wait_result("cmd-1", 1)
    thread.join()
    assert result == CommandResult("cmd-1", True, None)
    assert box["result"] == [result]


def test_wait_result_times_out_to_none():
    queue = CommandQueue(new_id=counting_ids())
    assert queue.wait_result("missing", 0.05) is None


def test_take_blocks_then_wakes_on_enqueue():
    queue = CommandQueue(new_id=counting_ids())
    box = {}

    def take():
        box["commands"] = queue.take(KEY, 1000, 1)

    thread = _thread(take)
    time.sleep(0.05)
    queue.enqueue(KEY, "abort", {}, 1000)
    thread.join()
    assert [command.command_id for command in box["commands"]] == ["cmd-1"]


def test_close_wakes_waiters():
    queue = CommandQueue(new_id=counting_ids())
    box = {}
    result_box = {}

    def take():
        box["commands"] = queue.take(KEY, 1000, 2)

    def wait_result():
        result_box["result"] = queue.wait_result("cmd-1", 2)

    take_thread = _thread(take)
    result_thread = _thread(wait_result)
    time.sleep(0.05)
    queue.close()
    take_thread.join()
    result_thread.join()
    assert box["commands"] == []
    assert result_box["result"] is None


def test_queue_full_returns_none():
    queue = CommandQueue(max_per_key=2, new_id=counting_ids())
    assert queue.enqueue(KEY, "abort", {}, 1000) is not None
    assert queue.enqueue(KEY, "abort", {}, 1000) is not None
    assert queue.enqueue(KEY, "abort", {}, 1000) is None


def test_drop_key_returns_undelivered():
    queue = CommandQueue(new_id=counting_ids())
    queue.enqueue(KEY, "abort", {}, 1000)
    queue.enqueue(KEY, "abort", {}, 1000)
    dropped = queue.drop_key(KEY)
    assert [command.command_id for command in dropped] == ["cmd-1", "cmd-2"]
    assert queue.take(KEY, 1000, 0) == []


def test_default_ids_are_unique_across_queues():
    first = CommandQueue().enqueue(KEY, "abort", {}, 1000)
    second = CommandQueue().enqueue(KEY, "abort", {}, 1000)
    assert first.command_id != second.command_id
    assert re.fullmatch(r"cmd-[0-9a-f]{32}", first.command_id)
