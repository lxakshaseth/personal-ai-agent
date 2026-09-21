"""
Sliding-Window Conversation Manager for Real-Time Conversational Voice.
Maintains recent conversational turns, optimizes token usage, and formats
prompts specifically for natural, conversational voice interaction.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

VOICE_SYSTEM_PROMPT = """\
You are NOVA, a real-time conversational AI desktop assistant.
You are speaking directly to the user through their speakers or headphones.

Rules for voice output:
1. Be concise, direct, and conversational (1 to 2 sentences per response unless asked for detail).
2. Never output markdown formatting, asterisks, bullet points, raw code, or URLs unless explicitly requested.
3. Speak naturally, as if having a fluid spoken phone or voice call.
4. If asked to control the computer or open apps/sites, confirm concisely what you are doing.
"""


class ConversationManager:
    """
    Manages conversational turns with sliding window pruning to ensure low latency
    and prevent token overflow during extended voice sessions.
    """

    def __init__(
        self,
        max_turns: int = 8,
        system_prompt: str = VOICE_SYSTEM_PROMPT,
    ) -> None:
        self.max_turns = max_turns
        self.system_prompt = system_prompt
        self._history: List[Dict[str, str]] = []

    def get_history(self) -> List[Dict[str, str]]:
        return list(self._history)

    def add_user_message(self, content: str) -> None:
        """Record a user spoken prompt."""
        clean = content.strip()
        if clean:
            self._history.append({"role": "user", "content": clean})
            self._prune()

    def add_assistant_message(self, content: str) -> None:
        """Record an assistant response."""
        clean = content.strip()
        if clean:
            self._history.append({"role": "assistant", "content": clean})
            self._prune()

    def _prune(self) -> None:
        """Keep only the most recent max_turns messages."""
        if len(self._history) > self.max_turns * 2:
            # Keep the last max_turns pairs of user/assistant
            self._history = self._history[-(self.max_turns * 2):]

    def get_messages(self, current_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        """
        Assemble the full message payload including system prompt,
        sliding history, and the optional current user prompt.
        """
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.system_prompt}
        ]
        messages.extend(self._history)
        if current_prompt and current_prompt.strip():
            messages.append({"role": "user", "content": current_prompt.strip()})
        return messages

    def clear(self) -> None:
        """Reset conversation history."""
        self._history.clear()


# Default singleton instance
_conv_manager: Optional[ConversationManager] = None


def get_conversation_manager() -> ConversationManager:
    global _conv_manager
    if _conv_manager is None:
        _conv_manager = ConversationManager()
    return _conv_manager
