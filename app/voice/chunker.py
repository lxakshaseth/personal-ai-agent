"""
Intelligent Response Chunker for Streaming Conversational TTS.
Buffers streaming LLM tokens until a natural speech boundary (sentence punctuation,
sub-clause comma/semicolon, or safe word length) is reached, immediately yielding
fluent chunks for non-blocking concurrent TTS playback.
"""
from __future__ import annotations

import re
from typing import List, Optional


class ResponseChunker:
    """
    Adaptive text buffer that breaks streaming LLM generation into natural speech units.

    Ensures the user hears audio within ~300-500ms of generation onset without
    awkward 1-word audio interruptions.
    """

    # Sentence boundary regex (period, question mark, exclamation point followed by space or newline)
    SENTENCE_END = re.compile(r'([.?!]+(?:\s+|\n+|$))')
    # Clause boundary regex (comma, colon, semicolon followed by space)
    CLAUSE_END = re.compile(r'([,;:]\s+)')

    def __init__(
        self,
        min_words_for_clause: int = 4,
        max_words_before_force_split: int = 12,
    ) -> None:
        self.min_words_for_clause = min_words_for_clause
        self.max_words_before_force_split = max_words_before_force_split
        self._buffer = ""
        self._total_chunks_emitted = 0

    def reset(self) -> None:
        """Clear the chunker buffer."""
        self._buffer = ""
        self._total_chunks_emitted = 0

    def add_token(self, token: str) -> List[str]:
        """
        Add an incoming LLM token to the buffer.
        Returns a list of any newly completed speech chunks ready for TTS.
        """
        if not token:
            return []

        self._buffer += token
        ready_chunks: List[str] = []

        while True:
            chunk = self._extract_next_chunk()
            if chunk:
                ready_chunks.append(chunk)
                self._total_chunks_emitted += 1
            else:
                break

        return ready_chunks

    def _extract_next_chunk(self) -> Optional[str]:
        """Check the current buffer for a valid speech chunk boundary."""
        if not self._buffer.strip():
            return None

        # 1. Check for sentence end: ., ?, !, \n
        match = self.SENTENCE_END.search(self._buffer)
        if match:
            split_idx = match.end()
            chunk = self._buffer[:split_idx].strip()
            self._buffer = self._buffer[split_idx:]
            if chunk:
                return chunk

        # 2. Check for clause boundary (comma, semicolon) if buffer is long enough
        words = self._buffer.split()
        if len(words) >= self.min_words_for_clause:
            clause_match = self.CLAUSE_END.search(self._buffer)
            if clause_match and clause_match.end() < len(self._buffer):
                # Ensure the clause has enough words
                clause_text = self._buffer[:clause_match.end()].strip()
                if len(clause_text.split()) >= self.min_words_for_clause:
                    split_idx = clause_match.end()
                    chunk = self._buffer[:split_idx].strip()
                    self._buffer = self._buffer[split_idx:]
                    return chunk

        # 3. Fallback: if user writes a long run-on sentence without punctuation (> max_words)
        if len(words) >= self.max_words_before_force_split:
            # Find the last whitespace before max_words
            match_space = re.search(r'\s+', self._buffer)
            if match_space:
                parts = self._buffer.split(maxsplit=self.max_words_before_force_split)
                if len(parts) > self.max_words_before_force_split:
                    chunk = " ".join(parts[:self.max_words_before_force_split]).strip()
                    # Reconstruct remainder
                    self._buffer = parts[-1]
                    return chunk

        return None

    def flush(self) -> Optional[str]:
        """Flush and return any remaining buffered text when generation finishes."""
        remaining = self._buffer.strip()
        self._buffer = ""
        if remaining:
            self._total_chunks_emitted += 1
            return remaining
        return None
