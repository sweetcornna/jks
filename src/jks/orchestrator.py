from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from .agent import AgentReply
from .expression import ExpressionEngine, TurnState


@dataclass(frozen=True)
class TurnResult:
    user_text: str
    agent_text: str
    emotion: str


class ConversationOrchestrator:
    def __init__(self, recorder, speech, agent, display, player, voice: str):
        self.recorder = recorder
        self.speech = speech
        self.agent = agent
        self.display = display
        self.player = player
        self.voice = voice
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
        user_text = self.speech.transcribe(audio_path)

        self._set_state(TurnState.THINKING)
        reply: AgentReply = self.agent.send_message(user_text, self.conversation_id)

        self._set_state(TurnState.SPEAKING)
        audio_reply = self.speech.synthesize(reply.text, self.voice)
        self.player.play(audio_reply)

        final_intent = self.expression.intent_from_agent(
            {
                "emotion": reply.emotion or "happy",
                "display_text": reply.display_text if reply.display_text is not None else "DONE",
                "duration_ms": reply.duration_ms,
                "intensity": reply.intensity,
            }
        )
        self._show_intent(final_intent)
        self.state = TurnState.IDLE
        return TurnResult(
            user_text=user_text,
            agent_text=reply.text,
            emotion=final_intent.emotion,
        )

    def _show_state(self, state: TurnState) -> None:
        self._show_intent(self.expression.intent_for_state(state))

    def _set_state(self, state: TurnState) -> None:
        self.state = state
        self._show_state(state)

    def _require_idle(self) -> None:
        if self.state != TurnState.IDLE:
            raise RuntimeError("voice turn already active")

    def _show_intent(self, intent) -> None:
        try:
            self.display.show(intent)
        except Exception:
            return None
