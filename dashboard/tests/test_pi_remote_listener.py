import http.client
import logging
import os
import socket
import stat

from pi_remote.contract import JsonResponse
from pi_remote.listener import UdsListener


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path, timeout=5):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def _get(socket_path):
    connection = UnixHTTPConnection(socket_path)
    try:
        connection.request("GET", "/v1/health")
        response = connection.getresponse()
        response.read()
        return response.status
    finally:
        connection.close()


def _handler(method, path, body):
    return JsonResponse(200, {"ok": True, "method": method, "path": path, "body": body})


def _socket_dir(tmp_path, name="sockdir"):
    directory = tmp_path / name
    directory.mkdir()
    os.chmod(directory, 0o700)
    return directory


def test_start_binds_a_0600_socket_and_stop_removes_it(tmp_path):
    directory = _socket_dir(tmp_path)
    socket_path = str(directory / "pi.sock")
    listener = UdsListener(socket_path, _handler)
    listener.start()
    assert listener.running
    assert listener.bind_error is None
    assert stat.S_ISSOCK(os.stat(socket_path).st_mode)
    assert stat.S_IMODE(os.stat(socket_path).st_mode) == 0o600
    listener.stop()
    assert not listener.running
    assert not os.path.exists(socket_path)


def test_existing_directory_with_group_permissions_is_refused(tmp_path):
    directory = _socket_dir(tmp_path)
    os.chmod(directory, 0o755)
    listener = UdsListener(str(directory / "pi.sock"), _handler)
    listener.start()
    assert not listener.running
    assert listener.bind_error is not None
    assert "0700" in listener.bind_error
    assert not os.path.exists(str(directory / "pi.sock"))


def test_missing_directory_is_created_0700(tmp_path):
    socket_path = str(tmp_path / "new" / "pi.sock")
    listener = UdsListener(socket_path, _handler)
    listener.start()
    assert listener.running
    assert stat.S_IMODE(os.stat(tmp_path / "new").st_mode) == 0o700
    listener.stop()


def test_stale_socket_file_is_replaced(tmp_path):
    directory = _socket_dir(tmp_path)
    socket_path = directory / "pi.sock"
    socket_path.write_text("stale")
    listener = UdsListener(str(socket_path), _handler)
    listener.start()
    assert listener.running
    assert stat.S_ISSOCK(os.stat(socket_path).st_mode)
    listener.stop()


def test_live_socket_is_a_bind_error(tmp_path):
    directory = _socket_dir(tmp_path)
    socket_path = str(directory / "pi.sock")
    first = UdsListener(socket_path, _handler)
    first.start()
    assert first.running
    second = UdsListener(socket_path, _handler)
    second.start()
    assert not second.running
    assert second.bind_error is not None
    assert "already in use" in second.bind_error
    assert first.running
    second.stop()
    first.stop()
    assert not os.path.exists(socket_path)



def test_successful_requests_log_at_debug(tmp_path, caplog):
    directory = _socket_dir(tmp_path)
    listener = UdsListener(str(directory / "pi.sock"), _handler)
    listener.start()
    caplog.set_level(logging.DEBUG, logger="pi_remote.listener")
    assert _get(str(directory / "pi.sock")) == 200
    records = [record for record in caplog.records if record.name == "pi_remote.listener"]
    assert any(
        record.levelno == logging.DEBUG
        and "GET /v1/health -> 200" in record.getMessage()
        for record in records
    )
    assert not any(
        record.levelno == logging.INFO
        and "GET /v1/health" in record.getMessage()
        for record in records
    )
    listener.stop()
