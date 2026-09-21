"""
Voice Controller — orchestrates Microphone -> STT -> Agent -> TTS.

Provides:
  - VoiceController: main coordination engine
  - Wake-word filtering ("Jarvis, open YouTube" -> "open YouTube")
  - Graceful degradation: falls back to keyboard text input if microphone is unavailable
  - CLI loop: python -m app.voice.voice_controller
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
from typing import Optional

from app.agent.agent import PersonalAgent, build_agent
from app.agent.base import AgentInput
from app.config.settings import Settings, get_settings
from app.utils.exceptions import (
    MicrophoneUnavailableError,
    NoSpeechDetectedError,
    SpeechRecognitionError,
    TextToSpeechError,
    VoiceError,
    VoiceTimeoutError,
)
from app.voice.microphone import MicrophoneRecorder
from app.voice.schemas import (
    AudioData,
    VoiceCommandResult,
    WakeWordCheckResult,
)
from app.voice.speech_to_text import SpeechToTextProvider, get_stt_provider
from app.voice.text_to_speech import TextToSpeechProvider, get_tts_provider

logger = logging.getLogger(__name__)


class VoiceController:
    """
    Coordinates the voice interaction loop:
      1. Records spoken audio (on-demand) via MicrophoneRecorder
      2. Transcribes via SpeechToTextProvider
      3. Checks/strips wake word if enabled
      4. Invokes PersonalAgent
      5. Speaks response via TextToSpeechProvider
    """

    def __init__(
        self,
        agent: Optional[PersonalAgent] = None,
        recorder: Optional[MicrophoneRecorder] = None,
        stt_provider: Optional[SpeechToTextProvider] = None,
        tts_provider: Optional[TextToSpeechProvider] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.agent = agent or build_agent()
        self.recorder = recorder or MicrophoneRecorder()
        self.stt = stt_provider or get_stt_provider(self.settings.stt_provider)
        self.tts = tts_provider or get_tts_provider(self.settings.tts_provider)

    # ── Wake Word Processing ──────────────────────────────────────────────────

    def check_wake_word(self, transcript: str) -> WakeWordCheckResult:
        """
        Check if the transcript contains the configured wake word.

        If WAKE_WORD_ENABLED=False:
            Returns detected=True with the entire command intact.

        If WAKE_WORD_ENABLED=True:
            Looks for the wake word (e.g. 'Jarvis') at the start or within the phrase.
            Strips the wake word and leading punctuation.
        """
        raw_text = transcript.strip()
        if not self.settings.wake_word_enabled:
            return WakeWordCheckResult(
                detected=True,
                wake_word=None,
                command_text=raw_text,
            )

        wake_word = self.settings.wake_word.strip()
        pattern = rf"^\s*{re.escape(wake_word)}[\s,:\-!]*"
        match = re.search(pattern, raw_text, re.IGNORECASE)

        if match:
            cleaned = raw_text[match.end():].strip()
            return WakeWordCheckResult(
                detected=True,
                wake_word=wake_word,
                command_text=cleaned,
            )

        # Also check anywhere in sentence (e.g. "hey Jarvis open chrome")
        inner_pattern = rf"\b{re.escape(wake_word)}\b[\s,:\-!]*"
        inner_match = re.search(inner_pattern, raw_text, re.IGNORECASE)
        if inner_match:
            # take text after the wake word
            cleaned = raw_text[inner_match.end():].strip()
            return WakeWordCheckResult(
                detected=True,
                wake_word=wake_word,
                command_text=cleaned or raw_text,
            )

        return WakeWordCheckResult(
            detected=False,
            wake_word=wake_word,
            command_text="",
        )

    # ── Single Turn Execution ─────────────────────────────────────────────────

    async def process_audio(self, audio: AudioData) -> VoiceCommandResult:
        """
        Transcribe audio, execute the command through the agent, and speak the response.
        """
        # 1. Speech-to-text
        try:
            stt_result = await self.stt.transcribe(audio)
            raw_transcript = stt_result.text.strip()
        except Exception as exc:
            logger.error("STT transcription failed: %s", exc)
            return VoiceCommandResult(
                raw_transcript="",
                command_text="",
                success=False,
                error=f"Speech recognition failed: {exc}",
            )

        if not raw_transcript:
            return VoiceCommandResult(
                raw_transcript="",
                command_text="",
                success=False,
                error="No speech detected.",
            )

        # 2. Wake-word check
        wake_result = self.check_wake_word(raw_transcript)
        if not wake_result.detected:
            logger.info("Wake word '%s' not detected in %r", self.settings.wake_word, raw_transcript)
            return VoiceCommandResult(
                raw_transcript=raw_transcript,
                command_text="",
                wake_word_detected=False,
                success=True,
                error=f"Wake word '{self.settings.wake_word}' not detected.",
            )

        command_text = wake_result.command_text or raw_transcript
        return await self.execute_command(command_text, raw_transcript=raw_transcript, wake_word_detected=True)

    async def execute_command(
        self,
        command: str,
        *,
        raw_transcript: Optional[str] = None,
        wake_word_detected: bool = False,
    ) -> VoiceCommandResult:
        """
        Execute a text or transcribed command through the agent and speak the response.
        """
        raw_text = raw_transcript or command
        clean_command = command.strip()

        if not clean_command:
            return VoiceCommandResult(
                raw_transcript=raw_text,
                command_text="",
                wake_word_detected=wake_word_detected,
                success=False,
                error="Empty command after wake-word parsing.",
            )

        # 3. Agent execution
        try:
            agent_output = await self.agent.run(AgentInput(command=clean_command))
            response_text = agent_output.response
        except Exception as exc:
            logger.exception("Agent execution failed: %s", exc)
            error_msg = f"Agent failed: {exc}"
            await self._safe_speak("Sorry, I encountered an error executing that command.")
            return VoiceCommandResult(
                raw_transcript=raw_text,
                command_text=clean_command,
                wake_word_detected=wake_word_detected,
                success=False,
                error=error_msg,
            )

        # 4. Text-to-speech output
        await self._safe_speak(response_text)

        return VoiceCommandResult(
            raw_transcript=raw_text,
            command_text=clean_command,
            wake_word_detected=wake_word_detected,
            success=agent_output.success,
            spoken_response=response_text,
            agent_output={
                "success": agent_output.success,
                "response": agent_output.response,
                "tool_calls": agent_output.tool_calls,
                "error": agent_output.error,
            },
            error=agent_output.error,
        )

    async def _safe_speak(self, text: str) -> None:
        """Speak text aloud without letting TTS failures crash the caller."""
        if not text:
            return
        try:
            await self.tts.speak(text)
        except Exception as exc:
            logger.warning("TTS speech failed: %s", exc)

    # ── Interactive CLI Loop ──────────────────────────────────────────────────

    async def run_cli(self) -> None:
        """
        Run the interactive CLI voice/text loop:
          - If microphone is available & VOICE_ENABLED=True: listens for speech
          - If microphone unavailable or user prefers: falls back to keyboard input
        """
        print("=" * 60)
        print("Personal AI Agent — Voice Interface")
        print(f"STT Provider:       {self.settings.stt_provider}")
        print(f"TTS Provider:       {self.settings.tts_provider}")
        print(f"Wake Word Enabled:  {self.settings.wake_word_enabled} ({self.settings.wake_word})")
        print(f"Voice Enabled:      {self.settings.voice_enabled}")
        print("Type 'exit' or press Ctrl+C to quit.")
        print("=" * 60)

        use_mic = self.settings.voice_enabled and self.recorder.is_available()
        if not use_mic:
            if not self.settings.voice_enabled:
                print("[Info] Voice is disabled in settings (VOICE_ENABLED=false). Using keyboard text mode.")
            else:
                print("[Notice] No microphone detected. Using keyboard text mode.")

        while True:
            try:
                if use_mic:
                    print("\nListening...")
                    try:
                        audio = await self.recorder.record_phrase(timeout=5.0, phrase_time_limit=8.0)
                        print("Processing speech...")
                        result = await self.process_audio(audio)
                    except NoSpeechDetectedError:
                        print("(No speech detected)")
                        continue
                    except MicrophoneUnavailableError as e:
                        print(f"[Warning] {e}. Switching to keyboard input.")
                        use_mic = False
                        continue
                    except VoiceTimeoutError:
                        print("(Timed out waiting for speech)")
                        continue
                    except Exception as e:
                        print(f"[Error] Recording error: {e}")
                        continue
                else:
                    # Keyboard text mode fallback
                    try:
                        loop = asyncio.get_running_loop()
                        command = await loop.run_in_executor(None, input, "\nEnter command: ")
                    except EOFError:
                        break

                    if not command or not command.strip():
                        continue
                    if command.strip().lower() in ("exit", "quit", "q"):
                        print("Goodbye!")
                        break

                    result = await self.execute_command(command.strip())

                # Print formatted result matching requested format
                if result.raw_transcript:
                    print(f'\nUser:\n"{result.raw_transcript}"')

                if result.agent_output and result.agent_output.get("tool_calls"):
                    calls = result.agent_output["tool_calls"]
                    tools_str = ", ".join(tc.get("tool", "") for tc in calls)
                    print(f"\nAgent:\ntool = {tools_str}")
                    print("\nExecution:")
                    for tc in calls:
                        status = "succeeded" if tc.get("success") else "failed"
                        output = tc.get("output") or tc.get("error") or ""
                        print(f"- {tc.get('tool')}: {output}")

                if result.spoken_response:
                    print(f'\nVoice response:\n"{result.spoken_response}"')
                elif result.error:
                    print(f"\n[Error]: {result.error}")

            except KeyboardInterrupt:
                print("\nInterrupted by user. Exiting.")
                break
            except Exception as e:
                logger.exception("Unexpected error in CLI loop: %s", e)
                print(f"\n[Unexpected Error]: {e}")


# ── Module Execution (python -m app.voice.voice_controller) ───────────────────

def main() -> None:
    """Entry point for python -m app.voice.voice_controller."""
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    from app.agent.tool_registry import load_all_tools
    load_all_tools()

    controller = VoiceController()
    try:
        asyncio.run(controller.run_cli())
    except KeyboardInterrupt:
        print("\nGoodbye!")



if __name__ == "__main__":
    main()
