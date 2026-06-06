from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from .agent import AgentReply, AgentTraceEvent
from .expression import DisplayCommand, ExpressionEngine, TurnState


@dataclass(frozen=True)
class TurnResult:
    user_text: str
    agent_text: str
    emotion: str
    audio_error: str = ""
    display_text: str = ""
    display_duration_ms: int = 0
    display_intensity: str = ""


class TurnFailure(RuntimeError):
    def __init__(self, message: str, user_text: str = "", audio_path: object = ""):
        super().__init__(message)
        self.user_text = user_text
        self.audio_path = Path(audio_path) if audio_path else None


class ConversationOrchestrator:
    def __init__(
        self,
        recorder,
        speech,
        agent,
        display,
        player,
        voice: str,
        status_callback: Optional[Callable[[TurnState], None]] = None,
        display_error_callback: Optional[Callable[[str], None]] = None,
        agent_trace_callback: Optional[Callable[[AgentTraceEvent], None]] = None,
        display_update_callback: Optional[Callable[[object], None]] = None,
    ):
        self.recorder = recorder
        self.speech = speech
        self.agent = agent
        self.display = display
        self.player = player
        self.voice = voice
        self.status_callback = status_callback
        self.display_error_callback = display_error_callback
        self.agent_trace_callback = agent_trace_callback
        self.display_update_callback = display_update_callback
        self._display_error_reported = False
        self.expression = ExpressionEngine()
        self.conversation_id = str(uuid4())
        self.state = TurnState.IDLE

    def run_voice_turn(self) -> TurnResult:
        try:
            self._require_idle()
            self._set_state(TurnState.LISTENING)
            audio_path = self.recorder.record_fixed_seconds()
            return self._process_audio(audio_path)
        except Exception:
            self._set_state(TurnState.ERROR)
            self.state = TurnState.IDLE
            raise

    def start_recording(self) -> None:
        self._require_idle()
        try:
            self._set_state(TurnState.LISTENING)
            self.recorder.start_recording()
        except Exception:
            self._set_state(TurnState.ERROR)
            self.state = TurnState.IDLE
            raise

    def finish_voice_turn(self) -> TurnResult:
        if self.state != TurnState.LISTENING:
            raise RuntimeError("recording is not in progress")
        try:
            audio_path = self.recorder.stop_recording()
            return self._process_audio(audio_path)
        except Exception:
            self._set_state(TurnState.ERROR)
            self.state = TurnState.IDLE
            raise

    def _process_audio(self, audio_path) -> TurnResult:
        self._set_state(TurnState.TRANSCRIBING)
        try:
            user_text = self.speech.transcribe(audio_path)
        except Exception as exc:
            raise TurnFailure(str(exc), audio_path=audio_path) from exc
        if not user_text.strip():
            raise TurnFailure("empty transcript", audio_path=audio_path)

        self._set_state(TurnState.THINKING)
        try:
            reply: AgentReply = self.agent.send_message(
                user_text,
                self.conversation_id,
                trace_callback=self.agent_trace_callback,
            )
        except Exception as exc:
            raise TurnFailure(str(exc), user_text=user_text, audio_path=audio_path) from exc

        self._set_state(TurnState.SPEAKING)
        audio_error = ""
        try:
            synthesize_and_play = getattr(self.speech, "synthesize_and_play", None)
            if callable(synthesize_and_play):
                synthesize_and_play(reply.text, self.voice, self.player)
            else:
                audio_reply = self.speech.synthesize(reply.text, self.voice)
                self.player.play(audio_reply)
        except Exception as exc:
            audio_error = str(exc)

        if audio_error:
            final_actions = [DisplayCommand("show", self.expression.intent_for_state(TurnState.ERROR))]
        else:
            display_payload = {
                "emotion": reply.emotion or "happy",
                "display_text": reply.display_text if reply.display_text is not None else "DONE",
                "duration_ms": reply.duration_ms,
                "intensity": reply.intensity,
                "display_sequence": reply.display_sequence,
                "display_commands": reply.display_commands,
            }
            action_builder = getattr(self.expression, "display_actions_from_agent", None)
            if callable(action_builder):
                final_actions = action_builder(display_payload)
            else:
                final_actions = [DisplayCommand("show", self.expression.intent_from_agent(display_payload))]

        final_intent = None
        for action in final_actions:
            shown_intent = self._show_display_action(action)
            if shown_intent is not None:
                final_intent = shown_intent

        if final_intent is None:
            final_intent = self.expression.intent_from_agent({"emotion": "neutral"})
        self.state = TurnState.IDLE
        return TurnResult(
            user_text=user_text,
            agent_text=reply.text,
            emotion=final_intent.emotion,
            audio_error=audio_error,
            display_text=final_intent.text,
            display_duration_ms=final_intent.duration_ms,
            display_intensity=final_intent.intensity,
        )

    def _show_state(self, state: TurnState) -> None:
        self._show_intent(self.expression.intent_for_state(state))

    def _set_state(self, state: TurnState) -> None:
        self.state = state
        self._emit_status(state)
        self._show_state(state)

    def _require_idle(self) -> None:
        if self.state != TurnState.IDLE:
            raise RuntimeError("voice turn already active")

    def _show_intent(self, intent) -> None:
        self._emit_display_update(intent)
        try:
            self.display.show(intent)
        except Exception as exc:
            self._emit_display_error(f"OLED update failed: {exc}")
            return None

    def _show_display_action(self, action: DisplayCommand):
        if action.command == "clear":
            self._clear_display()
            return None
        if action.command == "show" and action.intent is not None:
            self._show_intent(action.intent)
            return action.intent
        return None

    def _clear_display(self) -> None:
        self._emit_display_update(None)
        try:
            self.display.clear()
        except Exception as exc:
            self._emit_display_error(f"OLED update failed: {exc}")
            return None

    def _emit_status(self, state: TurnState) -> None:
        if self.status_callback is None:
            return None
        try:
            self.status_callback(state)
        except Exception:
            return None

    def _emit_display_error(self, message: str) -> None:
        if self.display_error_callback is None or self._display_error_reported:
            return None
        self._display_error_reported = True
        try:
            self.display_error_callback(message)
        except Exception:
            return None

    def _emit_display_update(self, intent) -> None:
        if self.display_update_callback is None:
            return None
        try:
            self.display_update_callback(intent)
        except Exception:
            return None
