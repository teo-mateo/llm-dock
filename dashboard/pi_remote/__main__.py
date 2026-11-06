import argparse
import logging
import threading
import time

from .supervisor import PiRemoteSupervisor

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the llm-dock pi-remote listener")
    parser.add_argument("--socket", required=True, help="Unix socket path")
    parser.add_argument("--db", required=True, help="pi_remote SQLite database path")
    parser.add_argument(
        "--send-abort-after",
        type=float,
        default=None,
        help="dev only: enqueue abort for live sessions after N seconds",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    supervisor = PiRemoteSupervisor(socket_path=args.socket, db_path=args.db)
    supervisor.start()
    status = supervisor.status()
    if not status["running"]:
        logger.error("pi remote listener failed: %s", status["bind_error"])
        return 1
    if args.send_abort_after is not None:
        threading.Thread(
            target=_send_abort,
            args=(supervisor, args.send_abort_after),
            name="pi-remote-dev-abort",
            daemon=True,
        ).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        supervisor.stop_all()
    return 0


def _send_abort(supervisor: PiRemoteSupervisor, delay: float) -> None:
    time.sleep(delay)
    for summary in supervisor.sessions():
        if not summary.live:
            continue
        command_id, error = supervisor.send_command(
            (summary.session_id, summary.instance_id), "abort", {}
        )
        logger.info("pi remote dev abort %s %s", command_id, error)


if __name__ == "__main__":
    raise SystemExit(main())
