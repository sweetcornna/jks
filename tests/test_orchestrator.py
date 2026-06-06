from __future__ import annotations

from pathlib import Path
import unittest

from jks.agent import AgentReply, parse_agent_reply
from jks.display import DisplayIntent
from jks.expression import ExpressionEngine
from jks.orchestrator import ConversationOrchestrator


class FakeRecorder:
    def __init__(self, fail=False):
        self.fail = fail
        self.recordings = 0

    def record_fixed_seconds(self, seconds=4.0):
        self.recordings += 1
        if self.fail:
            raise RuntimeError("recorder failed")
        return Path("/tmp/jks-test-input.wav")


class FakeSpeech:
    def __init__(self, user_text="hello", fail_transcribe=False, fail_synthesize=False):
        self.user_text = user_text
        self.fail_transcribe = fail_transcribe
        self.fail_synthesize = fail_synthesize
        self.transcribed = []
        self.synthesized = []

    def transcribe(self, audio_path):
        self.transcribed.append(audio_path)
        if self.fail_transcribe:
            raise RuntimeError("stt failed")
        return self.user_text

    def synthesize(self, text, voice):
        self.synthesized.append((text, voice))
        if self.fail_synthesize:
            raise RuntimeError("tts failed")
        return Path("/tmp/jks-test-reply.wav")


class FakeAgent:
    def __init__(self, reply=None, fail=False):
        self.reply = reply or AgentReply(text="reply", emotion="happy")
        self.fail = fail
        self.messages = []
        self.conversation_ids = []

    def send_message(self, text, conversation_id):
        self.messages.append(text)
        self.conversation_ids.append(conversation_id)
        if self.fail:
            raise RuntimeError("agent failed")
        return self.reply


class FakeDisplay:
    def __init__(self):
        self.intents = []

    def show(self, intent):
        self.intents.append(intent)


class FailingDisplay:
    def show(self, intent):
        raise OSError("oled disconnected")


class ErrorOnlyFailingDisplay(FakeDisplay):
    def show(self, intent):
        if intent.emotion == "error":
            raise OSError("error display failed")
        super().show(intent)


class FakePlayer:
    def __init__(self, fail=False):
        self.fail = fail
        self.played = []

    def play(self, audio_path):
        self.played.append(audio_path)
        if self.fail:
            raise RuntimeError("player failed")


class RecordingExpressionEngine:
    def __init__(self):
        self.real = ExpressionEngine()
        self.agent_payloads = []

    def intent_for_state(self, state):
        return self.real.intent_for_state(state)

    def intent_from_agent(self, payload):
        self.agent_payloads.append(dict(payload))
        return self.real.intent_from_agent(payload)


class OrchestratorTests(unittest.TestCase):
    def test_successful_voice_turn_updates_oled_in_order_and_returns_turn_result(self):
        display = FakeDisplay()
        player = FakePlayer()
        orchestrator = ConversationOrchestrator(
            recorder=FakeRecorder(),
            speech=FakeSpeech(user_text="hello"),
            agent=FakeAgent(reply=AgentReply(text="reply", emotion="happy")),
            display=display,
            player=player,
            voice="warm",
        )

        result = orchestrator.run_voice_turn()

        self.assertEqual(result.user_text, "hello")
        self.assertEqual(result.agent_text, "reply")
        self.assertEqual(result.emotion, "happy")
        self.assertEqual(
            [(intent.emotion, intent.text) for intent in display.intents],
            [
                ("listening", "HEAR"),
                ("thinking", "TEXT"),
                ("thinking", "WAIT"),
                ("speaking", "TALK"),
                ("happy", "DONE"),
            ],
        )
        self.assertEqual(player.played, [Path("/tmp/jks-test-reply.wav")])
        self.assertEqual(orchestrator.agent.messages, ["hello"])
        self.assertEqual(orchestrator.speech.synthesized, [("reply", "warm")])

    def test_agent_display_intent_fields_are_passed_to_expression_and_clamped(self):
        display = FakeDisplay()
        expression = RecordingExpressionEngine()
        orchestrator = ConversationOrchestrator(
            recorder=FakeRecorder(),
            speech=FakeSpeech(),
            agent=FakeAgent(
                reply=AgentReply(
                    text="reply",
                    emotion="surprised",
                    display_text="AGENT SAYS TOO MUCH",
                    duration_ms=999999,
                    intensity="overdrive",
                )
            ),
            display=display,
            player=FakePlayer(),
            voice="warm",
        )
        orchestrator.expression = expression

        orchestrator.run_voice_turn()

        self.assertEqual(
            expression.agent_payloads,
            [
                {
                    "emotion": "surprised",
                    "display_text": "AGENT SAYS TOO MUCH",
                    "duration_ms": 999999,
                    "intensity": "overdrive",
                }
            ],
        )
        self.assertEqual(
            display.intents[-1],
            DisplayIntent(
                emotion="surprised",
                text="AGENT SAYS TOO",
                duration_ms=5000,
                intensity="normal",
            ),
        )

    def test_parsed_nested_display_intent_is_still_clamped_by_expression(self):
        display = FakeDisplay()
        orchestrator = ConversationOrchestrator(
            recorder=FakeRecorder(),
            speech=FakeSpeech(),
            agent=FakeAgent(
                reply=parse_agent_reply(
                    {
                        "result": {
                            "text": "reply",
                            "display_intent": {
                                "emotion": "made-up",
                                "display_text": "THIS TEXT IS FAR TOO LONG FOR OLED",
                                "duration_ms": 999999,
                                "intensity": "unsafe",
                            },
                        }
                    }
                )
            ),
            display=display,
            player=FakePlayer(),
            voice="warm",
        )

        result = orchestrator.run_voice_turn()

        self.assertEqual(result.agent_text, "reply")
        self.assertEqual(result.emotion, "neutral")
        self.assertEqual(
            display.intents[-1],
            DisplayIntent(
                emotion="neutral",
                text="THIS TEXT IS F",
                duration_ms=5000,
                intensity="normal",
            ),
        )

    def test_missing_agent_emotion_defaults_to_happy_and_done_label(self):
        display = FakeDisplay()
        orchestrator = ConversationOrchestrator(
            recorder=FakeRecorder(),
            speech=FakeSpeech(),
            agent=FakeAgent(reply=AgentReply(text="reply")),
            display=display,
            player=FakePlayer(),
            voice="warm",
        )

        result = orchestrator.run_voice_turn()

        self.assertEqual(result.emotion, "happy")
        self.assertEqual(display.intents[-1], DisplayIntent(emotion="happy", text="DONE"))

    def test_speech_agent_and_player_failures_show_error_and_reraise(self):
        cases = [
            {"name": "recorder", "recorder": FakeRecorder(fail=True), "speech": FakeSpeech(), "agent": FakeAgent(), "player": FakePlayer()},
            {"name": "stt", "speech": FakeSpeech(fail_transcribe=True), "agent": FakeAgent(), "player": FakePlayer()},
            {"name": "tts", "speech": FakeSpeech(fail_synthesize=True), "agent": FakeAgent(), "player": FakePlayer()},
            {"name": "agent", "speech": FakeSpeech(), "agent": FakeAgent(fail=True), "player": FakePlayer()},
            {"name": "player", "speech": FakeSpeech(), "agent": FakeAgent(), "player": FakePlayer(fail=True)},
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                display = FakeDisplay()
                orchestrator = ConversationOrchestrator(
                    recorder=case.get("recorder", FakeRecorder()),
                    speech=case["speech"],
                    agent=case["agent"],
                    display=display,
                    player=case["player"],
                    voice="warm",
                )

                with self.assertRaises(RuntimeError):
                    orchestrator.run_voice_turn()

                self.assertEqual(display.intents[-1], DisplayIntent(emotion="error", text="OOPS"))

    def test_display_failures_do_not_interrupt_successful_voice_turn(self):
        player = FakePlayer()
        orchestrator = ConversationOrchestrator(
            recorder=FakeRecorder(),
            speech=FakeSpeech(user_text="hello"),
            agent=FakeAgent(reply=AgentReply(text="reply", emotion="happy")),
            display=FailingDisplay(),
            player=player,
            voice="warm",
        )

        result = orchestrator.run_voice_turn()

        self.assertEqual(result.user_text, "hello")
        self.assertEqual(result.agent_text, "reply")
        self.assertEqual(player.played, [Path("/tmp/jks-test-reply.wav")])

    def test_error_display_failure_preserves_original_exception(self):
        orchestrator = ConversationOrchestrator(
            recorder=FakeRecorder(),
            speech=FakeSpeech(),
            agent=FakeAgent(fail=True),
            display=ErrorOnlyFailingDisplay(),
            player=FakePlayer(),
            voice="warm",
        )

        with self.assertRaisesRegex(RuntimeError, "agent failed"):
            orchestrator.run_voice_turn()

    def test_conversation_id_is_stable_across_turns(self):
        agent = FakeAgent()
        orchestrator = ConversationOrchestrator(
            recorder=FakeRecorder(),
            speech=FakeSpeech(),
            agent=agent,
            display=FakeDisplay(),
            player=FakePlayer(),
            voice="warm",
        )

        orchestrator.run_voice_turn()
        orchestrator.run_voice_turn()

        self.assertEqual(len(agent.conversation_ids), 2)
        self.assertTrue(agent.conversation_ids[0])
        self.assertEqual(agent.conversation_ids[0], agent.conversation_ids[1])


if __name__ == "__main__":
    unittest.main()
