import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from port_conflicts import (
    PORT_IN_USE,
    PortOwner,
    duplicate_ports,
    find_port_owner,
    next_free_port,
    port_in_use_body,
    start_blocker,
)

SERVICES = {
    "a": {"port": 3301},
    "b": {"port": 3302, "inspect": True, "inspect_upstream_port": 34000},
}


def test_owner_is_found_by_port():
    assert find_port_owner(SERVICES, 3301) == PortOwner("a", "port")


def test_owner_is_found_by_inspect_upstream_port():
    assert find_port_owner(SERVICES, 34000) == PortOwner("b", "inspect_upstream_port")


def test_a_service_does_not_conflict_with_itself():
    assert find_port_owner(SERVICES, 3301, exclude="a") is None


def test_free_port_has_no_owner():
    assert find_port_owner(SERVICES, 3310) is None


def test_compose_only_port_is_an_owner():
    owner = find_port_owner(SERVICES, 3300, compose_ports={3300})

    assert owner is not None and owner.kind == "compose"


def test_port_strings_are_compared_as_ints():
    assert find_port_owner({"a": {"port": "3301"}}, 3301) == PortOwner("a", "port")


def test_duplicate_ports_reports_every_claimant():
    services = {
        "a": {"port": 3301},
        "b": {"port": 3301},
        "c": {"port": 3302, "inspect_upstream_port": 3301},
        "d": {"port": 3303},
    }

    assert duplicate_ports(services) == {3301: ["a", "b", "c"]}


def test_no_duplicates_in_a_clean_file():
    assert duplicate_ports(SERVICES) == {}


def test_start_blocked_by_a_running_owner():
    services = {"a": {"port": 3301}, "b": {"port": 3301}}

    assert start_blocker(services, "a", lambda n: n == "b") == PortOwner("b", "port")


def test_start_blocked_by_a_stopped_inspected_owner():
    services = {"a": {"port": 3301}, "b": {"port": 3301, "inspect": True}}

    assert start_blocker(services, "a", lambda n: False) == PortOwner("b", "port")


def test_start_not_blocked_by_a_stopped_plain_owner():
    services = {"a": {"port": 3301}, "b": {"port": 3301}}

    assert start_blocker(services, "a", lambda n: False) is None


def test_start_blocked_by_a_running_upstream_holder():
    services = {"a": {"port": 34000}, "b": {"port": 3302, "inspect_upstream_port": 34000}}

    assert start_blocker(services, "a", lambda n: True) == PortOwner("b", "inspect_upstream_port")


def test_next_free_port_skips_declared_and_compose_ports():
    services = {"a": {"port": 3300}, "b": {"port": 3302, "inspect_upstream_port": 3303}}

    assert next_free_port(services, {3301}, 3300, 3399) == 3304


def test_next_free_port_raises_when_exhausted():
    with pytest.raises(ValueError):
        next_free_port({"a": {"port": 3300}}, set(), 3300, 3300)


def test_body_is_flat_with_a_machine_code_and_names_the_owner():
    body = port_in_use_body(3301, PortOwner("a", "port"))

    assert body == {"error": "Port 3301 is already in use by service 'a'", "code": PORT_IN_USE}
