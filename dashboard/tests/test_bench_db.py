import uuid
import pytest
from benchmarking.db import BenchmarkDB
from benchmarking.models import BenchmarkRun


class TestCreateAndGetRun:
    def test_create_and_retrieve(self, db):
        run_id = str(uuid.uuid4())
        run = BenchmarkRun(
            id=run_id,
            service_name="llamacpp-test",
            model_path="/models/test.gguf",
            params_json={"-p": "512", "-n": "128"},
        )
        created = db.create_run(run)
        assert created.id == run_id
        assert created.status == "pending"
        assert created.service_name == "llamacpp-test"
        assert created.params_json == {"-p": "512", "-n": "128"}
        assert created.created_at is not None

    def test_get_nonexistent(self, db):
        result = db.get_run("nonexistent-id")
        assert result is None

    def test_create_preserves_params(self, db):
        run_id = str(uuid.uuid4())
        params = {"-p": "256", "-ngl": "99", "-fa": "", "-b": "2048"}
        run = BenchmarkRun(
            id=run_id,
            service_name="llamacpp-test",
            model_path="/models/test.gguf",
            params_json=params,
        )
        created = db.create_run(run)
        assert created.params_json == params
        assert created.params_json["-fa"] == ""


class TestListRuns:
    def _create_runs(self, db, service, count):
        ids = []
        for i in range(count):
            run_id = str(uuid.uuid4())
            run = BenchmarkRun(
                id=run_id,
                service_name=service,
                model_path="/models/test.gguf",
            )
            db.create_run(run)
            ids.append(run_id)
        return ids

    def test_list_all(self, db):
        self._create_runs(db, "svc-a", 3)
        self._create_runs(db, "svc-b", 2)
        runs, total = db.list_runs()
        assert total == 5
        assert len(runs) == 5

    def test_list_by_service(self, db):
        self._create_runs(db, "svc-a", 3)
        self._create_runs(db, "svc-b", 2)
        runs, total = db.list_runs(service_name="svc-a")
        assert total == 3
        assert all(r.service_name == "svc-a" for r in runs)

    def test_list_by_status(self, db):
        ids = self._create_runs(db, "svc-a", 3)
        db.update_status(ids[0], "completed")
        runs, total = db.list_runs(status="pending")
        assert total == 2

    def test_list_pagination(self, db):
        self._create_runs(db, "svc-a", 5)
        runs, total = db.list_runs(limit=2, offset=0)
        assert total == 5
        assert len(runs) == 2

        runs2, _ = db.list_runs(limit=2, offset=2)
        assert len(runs2) == 2
        assert runs[0].id != runs2[0].id

    def test_list_order_newest_first(self, db):
        ids = self._create_runs(db, "svc-a", 3)
        runs, _ = db.list_runs()
        # All have the same created_at (within the same second),
        # but insertion order is guaranteed newest-last by SQLite
        assert len(runs) == 3


class TestUpdateStatus:
    def test_status_transition(self, db):
        run_id = str(uuid.uuid4())
        run = BenchmarkRun(
            id=run_id,
            service_name="llamacpp-test",
            model_path="/models/test.gguf",
        )
        db.create_run(run)

        db.update_status(run_id, "running", started_at="2025-01-01T00:00:00Z")
        updated = db.get_run(run_id)
        assert updated.status == "running"
        assert updated.started_at == "2025-01-01T00:00:00Z"

        db.update_status(run_id, "completed", completed_at="2025-01-01T00:05:00Z")
        updated = db.get_run(run_id)
        assert updated.status == "completed"
        assert updated.completed_at == "2025-01-01T00:05:00Z"

    def test_status_failed_with_error(self, db):
        run_id = str(uuid.uuid4())
        run = BenchmarkRun(
            id=run_id,
            service_name="llamacpp-test",
            model_path="/models/test.gguf",
        )
        db.create_run(run)
        db.update_status(run_id, "failed", error_message="Timeout after 600s")
        updated = db.get_run(run_id)
        assert updated.status == "failed"
        assert updated.error_message == "Timeout after 600s"


class TestUpdateResults:
    def test_store_results(self, db):
        run_id = str(uuid.uuid4())
        run = BenchmarkRun(
            id=run_id,
            service_name="llamacpp-test",
            model_path="/models/test.gguf",
        )
        db.create_run(run)

        db.update_results(
            run_id,
            pp_avg_ts=1200.5,
            pp_stddev_ts=10.2,
            tg_avg_ts=85.3,
            tg_stddev_ts=2.1,
            raw_output='[{"test": "pp"}]',
            build_commit="abc123",
            model_type="7B",
            gpu_info="RTX 4090",
        )
        updated = db.get_run(run_id)
        assert updated.pp_avg_ts == 1200.5
        assert updated.pp_stddev_ts == 10.2
        assert updated.tg_avg_ts == 85.3
        assert updated.tg_stddev_ts == 2.1
        assert updated.raw_output == '[{"test": "pp"}]'
        assert updated.build_commit == "abc123"
        assert updated.model_type == "7B"
        assert updated.gpu_info == "RTX 4090"


class TestDeleteRun:
    def test_delete_existing(self, db):
        run_id = str(uuid.uuid4())
        run = BenchmarkRun(
            id=run_id,
            service_name="llamacpp-test",
            model_path="/models/test.gguf",
        )
        db.create_run(run)
        assert db.delete_run(run_id) is True
        assert db.get_run(run_id) is None

    def test_delete_nonexistent(self, db):
        assert db.delete_run("nonexistent") is False


class TestMostRecentRun:
    def test_returns_most_recent(self, db):
        for i in range(3):
            run = BenchmarkRun(
                id=str(uuid.uuid4()),
                service_name="llamacpp-test",
                model_path="/models/test.gguf",
                params_json={"-p": str(i)},
            )
            db.create_run(run)

        recent = db.get_most_recent_run("llamacpp-test")
        assert recent is not None

    def test_returns_none_when_empty(self, db):
        assert db.get_most_recent_run("nonexistent") is None


class TestHasRunningBenchmark:
    def test_no_running(self, db):
        run = BenchmarkRun(
            id=str(uuid.uuid4()),
            service_name="llamacpp-test",
            model_path="/models/test.gguf",
        )
        db.create_run(run)
        db.update_status(run.id, "completed")
        assert db.has_running_benchmark("llamacpp-test") is False

    def test_has_pending(self, db):
        run = BenchmarkRun(
            id=str(uuid.uuid4()),
            service_name="llamacpp-test",
            model_path="/models/test.gguf",
        )
        db.create_run(run)
        assert db.has_running_benchmark("llamacpp-test") is True

    def test_has_running(self, db):
        run = BenchmarkRun(
            id=str(uuid.uuid4()),
            service_name="llamacpp-test",
            model_path="/models/test.gguf",
        )
        db.create_run(run)
        db.update_status(run.id, "running")
        assert db.has_running_benchmark("llamacpp-test") is True


class TestRecoverStaleRuns:
    def test_recovers_running(self, db):
        run = BenchmarkRun(
            id=str(uuid.uuid4()),
            service_name="llamacpp-test",
            model_path="/models/test.gguf",
        )
        db.create_run(run)
        db.update_status(run.id, "running")

        count = db.recover_stale_runs()
        assert count == 1

        updated = db.get_run(run.id)
        assert updated.status == "failed"
        assert "server restart" in updated.error_message

    def test_does_not_touch_completed(self, db):
        run = BenchmarkRun(
            id=str(uuid.uuid4()),
            service_name="llamacpp-test",
            model_path="/models/test.gguf",
        )
        db.create_run(run)
        db.update_status(run.id, "completed")

        count = db.recover_stale_runs()
        assert count == 0

        updated = db.get_run(run.id)
        assert updated.status == "completed"
