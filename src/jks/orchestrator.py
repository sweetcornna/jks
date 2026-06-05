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

    def run_voice_turn(self) -> TurnResult:
        try:
            self._show_state(TurnState.LISTENING)
            audio_path = self.recorder.record_fixed_seconds()

            self._show_state(TurnState.TRANSCRIBING)
            user_text = self.speech.transcribe(audio_path)

            self._show_state(TurnState.THINKING)
            reply: AgentReply = self.agent.send_message(user_text, self.conversation_id)

            self._show_state(TurnState.SPEAKING)
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
            return TurnResult(
                user_text=user_text,
                agent_text=reply.text,
                emotion=final_intent.emotion,
            )
        except Exception:
            self._show_state(TurnState.ERROR)
            raise

    def _show_state(self, state: TurnState) -> None:
        self._show_intent(self.expression.intent_for_state(state))

    def _show_intent(self, intent) -> None:
        try:
            self.display.show(intent)
        except Exception:
            return None
