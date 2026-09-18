from inspector.ports import UPSTREAM_PORT_BAND, allocate_upstream_port


class TestAllocateUpstreamPort:
    def test_empty_services_returns_band_start(self):
        assert allocate_upstream_port({}, "svc-a") == 34000

    def test_skips_ports_taken_by_either_field(self):
        services = {
            "svc-a": {"port": 3301},
            "svc-b": {"port": 3302, "inspect_upstream_port": 34000},
            "svc-c": {"port": 3303, "inspect_upstream_port": 34001},
        }
        assert allocate_upstream_port(services, "svc-a") == 34002

    def test_own_public_port_is_not_allocatable(self):
        # A public port inside the band would collide with the proxy's own
        # 0.0.0.0 bind, so it counts as taken.
        assert allocate_upstream_port({"svc-a": {"port": 34000}}, "svc-a") == 34001

    def test_stable_for_service_that_already_has_one(self):
        services = {
            "svc-a": {"port": 3301, "inspect_upstream_port": 34005},
            "svc-b": {"port": 3302, "inspect_upstream_port": 34000},
        }
        assert allocate_upstream_port(services, "svc-a") == 34005

    def test_existing_upstream_port_wins_over_band_scan(self):
        services = {"svc-a": {"port": 3301, "inspect_upstream_port": 34999}}
        assert allocate_upstream_port(services, "svc-a") == 34999

    def test_raises_when_band_exhausted(self):
        services = {f"svc-{i}": {"port": 34000 + i} for i in range(len(UPSTREAM_PORT_BAND))}
        try:
            allocate_upstream_port(services, "svc-new")
            raise AssertionError("expected ValueError")
        except ValueError as e:
            assert "34000-34999" in str(e)
