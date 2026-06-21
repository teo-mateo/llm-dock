"""stream_chat_completion upstream-connection teardown (Phase 5 of #58).

Cooperative cancellation closes the generator (GeneratorExit); the streaming
`requests` response must be released in a finally either way, so a cancelled
run doesn't leak the model-server socket.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from chat import llm_proxy


class _FakeResp:
    def __init__(self, lines):
        self.status_code = 200
        self.encoding = None
        self._lines = lines
        self.closed = False

    def iter_lines(self, decode_unicode=True):
        for line in self._lines:
            yield line

    def close(self):
        self.closed = True


def _patch(monkeypatch, resp):
    monkeypatch.setattr(llm_proxy, "resolve_service",
                        lambda name: {"host_port": 1234, "api_key": "k"})
    monkeypatch.setattr(llm_proxy.requests, "post", lambda *a, **k: resp)


def test_response_closed_on_normal_completion(monkeypatch):
    resp = _FakeResp([
        'data: {"choices":[{"delta":{"content":"hi"}}]}',
        '',
        'data: [DONE]',
    ])
    _patch(monkeypatch, resp)

    events = list(llm_proxy.stream_chat_completion("svc", []))
    assert any(e[0] == "done" for e in events)
    assert resp.closed


def test_response_closed_on_early_generator_close(monkeypatch):
    # A long stream the consumer abandons mid-way (cooperative cancel).
    resp = _FakeResp([f'data: {{"choices":[{{"delta":{{"content":"t{i}"}}}}]}}'
                      for i in range(1000)])
    _patch(monkeypatch, resp)

    gen = llm_proxy.stream_chat_completion("svc", [])
    assert next(gen)[0] == "delta"   # consume one event, leaving the stream open
    gen.close()                      # GeneratorExit -> finally -> resp.close()
    assert resp.closed
