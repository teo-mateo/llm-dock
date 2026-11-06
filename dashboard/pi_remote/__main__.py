import argparse
import logging
import time

from .supervisor import PiRemoteSupervisor

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the llm-dock pi-remote listener")
    parser.add_argument("--socket", required=True, help="Unix socket path")
    parser.add_argument("--db", required=True, help="pi_remote SQLite database path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    supervisor = PiRemoteSupervisor(socket_path=args.socket, db_path=args.db)
    supervisor.start()
    status = supervisor.status()
    if not status["running"]:
        logger.error("pi remote listener failed: %s", status["bind_error"])
        return 1
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        supervisor.stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
