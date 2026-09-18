from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class Capture:
    id: str
    service_name: str
    method: str
    path: str

    model: Optional[str] = None
    template_type: Optional[str] = None
    status_code: Optional[int] = None
    stream: bool = False
    request_headers_json: Dict[str, str] = field(default_factory=dict)
    request_body: str = ""
    response_body: Optional[str] = None
    response_text: Optional[str] = None
    reasoning_text: Optional[str] = None
    tool_calls_json: Optional[str] = None
    finish_reason: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    ttfb_ms: Optional[int] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    request_truncated: bool = False
    response_truncated: bool = False
    created_at: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "service_name": self.service_name,
            "method": self.method,
            "path": self.path,
            "model": self.model,
            "template_type": self.template_type,
            "status_code": self.status_code,
            "stream": self.stream,
            "request_headers_json": self.request_headers_json,
            "request_body": self.request_body,
            "response_body": self.response_body,
            "response_text": self.response_text,
            "reasoning_text": self.reasoning_text,
            "tool_calls_json": self.tool_calls_json,
            "finish_reason": self.finish_reason,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "ttfb_ms": self.ttfb_ms,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "request_truncated": self.request_truncated,
            "response_truncated": self.response_truncated,
            "created_at": self.created_at,
        }
