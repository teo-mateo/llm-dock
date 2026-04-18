import json
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class Message:
    id: str
    conversation_id: str
    role: str
    content: str
    seq: int
    reasoning_content: Optional[str] = None
    model_service: Optional[str] = None
    images_json: Optional[str] = None
    tool_calls_json: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self):
        images = json.loads(self.images_json) if self.images_json else []
        tool_calls = json.loads(self.tool_calls_json) if self.tool_calls_json else []
        d = {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "reasoning_content": self.reasoning_content,
            "model_service": self.model_service,
            "images": images,
            "seq": self.seq,
            "created_at": self.created_at,
        }
        if tool_calls:
            d["tool_calls"] = tool_calls
        return d


@dataclass
class Critique:
    id: str
    message_id: str
    sidekick_service: str
    annotations_json: str = "[]"
    summary: Optional[str] = None
    verdict: Optional[str] = None
    raw_response: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "message_id": self.message_id,
            "sidekick_service": self.sidekick_service,
            "annotations": json.loads(self.annotations_json),
            "summary": self.summary,
            "verdict": self.verdict,
            "created_at": self.created_at,
        }


@dataclass
class Artifact:
    id: str
    message_id: str
    artifact_type: str
    content: str
    title: Optional[str] = None
    language: Optional[str] = None
    created_at: Optional[str] = None

    def to_dict(self):
        return {
            "id": self.id,
            "message_id": self.message_id,
            "type": self.artifact_type,
            "content": self.content,
            "title": self.title,
            "language": self.language,
            "created_at": self.created_at,
        }


@dataclass
class Conversation:
    id: str
    title: str
    main_service: str
    sidekick_service: Optional[str] = None
    main_system_prompt: str = ""
    sidekick_system_prompt: str = ""
    parent_conversation_id: Optional[str] = None
    selected_text: Optional[str] = None
    mcp_servers_json: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    messages: List[Message] = field(default_factory=list)

    def to_dict(self, include_messages=False):
        d = {
            "id": self.id,
            "title": self.title,
            "main_service": self.main_service,
            "sidekick_service": self.sidekick_service,
            "main_system_prompt": self.main_system_prompt,
            "sidekick_system_prompt": self.sidekick_system_prompt,
            "parent_conversation_id": self.parent_conversation_id,
            "selected_text": self.selected_text,
            "mcp_servers": json.loads(self.mcp_servers_json) if self.mcp_servers_json else [],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if include_messages:
            d["messages"] = [m.to_dict() for m in self.messages]
        return d
