"""会话管理：维护多轮对话上下文"""
from typing import Dict, List, Any
from dataclasses import dataclass, field


@dataclass
class Session:
    session_id: str
    messages: List[Dict[str, str]] = field(default_factory=list)
    # 提取的用户需求，避免重复传递完整对话历史
    requirements: Dict[str, Any] = field(default_factory=dict)
    # 本轮已查到的候选房源ID
    candidate_houses: List[str] = field(default_factory=list)


class SessionManager:
    def __init__(self):
        self._sessions: Dict[str, Session] = {}

    def get_or_create(self, session_id: str) -> Session:
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id=session_id)
        return self._sessions[session_id]

    def add_message(self, session_id: str, role: str, content: str):
        session = self.get_or_create(session_id)
        session.messages.append({"role": role, "content": content})

    def add_tool_result(self, session_id: str, tool_call_id: str, content: str):
        session = self.get_or_create(session_id)
        session.messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        })

    def get_messages(self, session_id: str) -> List[Dict[str, str]]:
        session = self.get_or_create(session_id)
        return session.messages

    def update_candidates(self, session_id: str, houses: List[str]):
        session = self.get_or_create(session_id)
        session.candidate_houses = houses

    def clear(self, session_id: str):
        if session_id in self._sessions:
            del self._sessions[session_id]


# 全局单例
session_manager = SessionManager()
