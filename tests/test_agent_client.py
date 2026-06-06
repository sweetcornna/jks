import json
import unittest
from unittest.mock import patch

from jks.agent import AgentProviderError, AgentReply, HttpAgentClient, parse_agent_reply


class AgentClientTests(unittest.TestCase):
    def test_agent_reply_defaults_to_empty_emotion(self):
        self.assertEqual(AgentReply(text="ok").emotion, "")

    def test_parse_structured_reply(self):
        reply = parse_agent_reply({"text": "你好", "emotion": "happy"})

        self.assertEqual(reply, AgentReply(text="你好", emotion="happy"))

    def test_parse_structured_reply_preserves_display_intent_fields(self):
        reply = parse_agent_reply(
            {
                "text": "ok",
                "emotion": "happy",
                "display_text": "OLED",
                "duration_ms": 1200,
                "intensity": "high",
            }
        )

        self.assertEqual(
            reply,
            AgentReply(
                text="ok",
                emotion="happy",
                display_text="OLED",
                duration_ms=1200,
                intensity="high",
            ),
        )

    def test_parse_openai_like_choice_message_content(self):
        reply = parse_agent_reply(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "choice answer",
                        }
                    }
                ]
            }
        )

        self.assertEqual(reply, AgentReply(text="choice answer"))

    def test_parse_nested_result_output_envelope(self):
        reply = parse_agent_reply(
            {
                "result": {
                    "output": {
                        "message": "nested answer",
                        "display": {
                            "emotion": "thinking",
                            "text": "WAIT",
                            "duration_ms": 1400,
                            "intensity": "normal",
                        },
                    }
                }
            }
        )

        self.assertEqual(
            reply,
            AgentReply(
                text="nested answer",
                emotion="thinking",
                display_text="WAIT",
                duration_ms=1400,
                intensity="normal",
            ),
        )

    def test_parse_messages_list_uses_last_assistant_message(self):
        reply = parse_agent_reply(
            {
                "messages": [
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": [{"type": "text", "text": "first"}]},
                    {"role": "assistant", "content": [{"type": "text", "text": "second"}]},
                ]
            }
        )

        self.assertEqual(reply, AgentReply(text="second"))

    def test_parse_response_content_parts(self):
        reply = parse_agent_reply(
            {
                "response": {
                    "content": [
                        {"type": "text", "text": "hello"},
                        {"type": "text", "text": " world"},
                    ]
                }
            }
        )

        self.assertEqual(reply, AgentReply(text="hello world"))

    def test_nested_unsupported_dict_is_not_stringified(self):
        reply = parse_agent_reply(
            {
                "result": {
                    "message": {
                        "role": "assistant",
                        "tool_calls": [{"text": "BAD"}],
                    }
                }
            }
        )

        self.assertEqual(reply, AgentReply(text=""))

    def test_unknown_content_parts_are_ignored(self):
        reply = parse_agent_reply(
            {
                "response": {
                    "content": [
                        {"type": "tool_call", "text": "BAD"},
                        {"type": "text", "text": "ok"},
                    ]
                }
            }
        )

        self.assertEqual(reply, AgentReply(text="ok"))

    def test_unsupported_direct_message_falls_back_to_choices(self):
        reply = parse_agent_reply(
            {
                "message": {"role": "assistant", "tool_calls": [{"text": "BAD"}]},
                "choices": [{"message": {"content": "safe fallback"}}],
            }
        )

        self.assertEqual(reply, AgentReply(text="safe fallback"))

    def test_top_level_text_dict_keeps_legacy_stringifying_behavior(self):
        reply = parse_agent_reply({"text": {"unexpected": "payload"}})

        self.assertEqual(reply, AgentReply(text="{'unexpected': 'payload'}"))

    def test_top_level_text_dict_does_not_parse_nested_text_key(self):
        reply = parse_agent_reply({"text": {"text": "inner"}})

        self.assertEqual(reply, AgentReply(text="{'text': 'inner'}"))

    def test_unknown_content_part_with_content_is_ignored(self):
        reply = parse_agent_reply(
            {
                "response": {
                    "content": [
                        {"type": "tool_call", "content": {"text": "BAD"}},
                        {"type": "text", "text": "ok"},
                    ]
                }
            }
        )

        self.assertEqual(reply, AgentReply(text="ok"))

    def test_text_content_part_with_unsupported_dict_text_is_ignored(self):
        reply = parse_agent_reply(
            {
                "response": {
                    "content": [
                        {"type": "text", "text": {"tool_calls": [{"text": "BAD"}]}},
                        {"type": "text", "text": "ok"},
                    ]
                }
            }
        )

        self.assertEqual(reply, AgentReply(text="ok"))

    def test_text_content_part_with_nested_text_dict_is_ignored(self):
        reply = parse_agent_reply(
            {
                "response": {
                    "content": [
                        {"type": "text", "text": {"text": "BAD"}},
                        {"type": "text", "text": "ok"},
                    ]
                }
            }
        )

        self.assertEqual(reply, AgentReply(text="ok"))

    def test_content_part_without_type_is_ignored(self):
        reply = parse_agent_reply(
            {
                "response": {
                    "content": [
                        {"content": {"text": "BAD"}},
                        {"text": "maybe"},
                        {"type": "text", "text": "ok"},
                    ]
                }
            }
        )

        self.assertEqual(reply, AgentReply(text="ok"))

    def test_outer_display_fields_survive_envelope_unwrap(self):
        reply = parse_agent_reply(
            {
                "emotion": "happy",
                "display_text": "DONE",
                "data": {"text": "answer"},
            }
        )

        self.assertEqual(reply, AgentReply(text="answer", emotion="happy", display_text="DONE"))

    def test_parse_structured_reply_accepts_reply_field(self):
        reply = parse_agent_reply({"reply": "fallback", "emotion": "thinking"})

        self.assertEqual(reply, AgentReply(text="fallback", emotion="thinking"))

    def test_parse_structured_reply_uses_reply_when_text_is_none(self):
        reply = parse_agent_reply({"text": None, "reply": "fallback"})

        self.assertEqual(reply, AgentReply(text="fallback"))

    def test_parse_structured_reply_defaults_to_empty_text_when_text_and_reply_missing(self):
        reply = parse_agent_reply({"emotion": "thinking"})

        self.assertEqual(reply, AgentReply(text="", emotion="thinking"))

    def test_parse_structured_reply_defaults_to_empty_text_when_text_and_reply_are_none(self):
        reply = parse_agent_reply({"text": None, "reply": None})

        self.assertEqual(reply, AgentReply(text=""))

    def test_parse_plain_text_reply(self):
        reply = parse_agent_reply("plain answer")

        self.assertEqual(reply.text, "plain answer")
        self.assertEqual(reply.emotion, "")

    def test_parse_other_payloads_by_stringifying(self):
        reply = parse_agent_reply(["unexpected", "payload"])

        self.assertEqual(reply, AgentReply(text="['unexpected', 'payload']"))

    def test_http_client_posts_message(self):
        class FakeResponse:
            status_code = 200
            content = json.dumps({"text": "ok", "emotion": "thinking"}).encode("utf-8")
            raised = False

            def raise_for_status(self):
                self.raised = True

            def json(self):
                return json.loads(self.content)

        response = FakeResponse()
        with patch("jks.agent.requests.post", return_value=response) as post:
            client = HttpAgentClient("http://127.0.0.1:8787/chat", "token")
            reply = client.send_message("hello", "conv-1")

        self.assertEqual(reply.text, "ok")
        self.assertEqual(reply.emotion, "thinking")
        self.assertTrue(response.raised)
        post.assert_called_once()
        self.assertEqual(post.call_args.args, ("http://127.0.0.1:8787/chat",))
        self.assertEqual(
            post.call_args.kwargs["json"],
            {"message": "hello", "conversation_id": "conv-1"},
        )
        self.assertEqual(
            post.call_args.kwargs["headers"]["Authorization"],
            "Bearer token",
        )
        self.assertEqual(post.call_args.kwargs["timeout"], 30.0)

    def test_http_client_omits_empty_authorization_token(self):
        class FakeResponse:
            text = "ok"

            def raise_for_status(self):
                pass

            def json(self):
                return {"text": "ok"}

        with patch("jks.agent.requests.post", return_value=FakeResponse()) as post:
            client = HttpAgentClient("http://127.0.0.1:8787/chat")
            client.send_message("hello", "conv-1")

        self.assertNotIn("Authorization", post.call_args.kwargs["headers"])

    def test_http_client_uses_openai_chat_payload_for_hermes_api_server_endpoint(self):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "hermes reply",
                            }
                        }
                    ]
                }

        with patch("jks.agent.requests.post", return_value=FakeResponse()) as post:
            client = HttpAgentClient("http://127.0.0.1:8642/v1/chat/completions", "api-key")
            reply = client.send_message("hello", "conv-1")

        self.assertEqual(reply, AgentReply(text="hermes reply"))
        self.assertEqual(
            post.call_args.kwargs["json"],
            {
                "model": "hermes-agent",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
        )
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer api-key")
        self.assertEqual(post.call_args.kwargs["headers"]["X-Hermes-Session-Id"], "conv-1")

    def test_http_client_does_not_send_empty_hermes_session_header(self):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": "ok"}}]}

        with patch("jks.agent.requests.post", return_value=FakeResponse()) as post:
            client = HttpAgentClient("http://127.0.0.1:8642/v1/chat/completions")
            client.send_message("hello", "")

        self.assertNotIn("X-Hermes-Session-Id", post.call_args.kwargs["headers"])

    def test_http_client_uses_text_when_json_parsing_fails(self):
        class FakeResponse:
            text = "plain response"

            def raise_for_status(self):
                pass

            def json(self):
                raise ValueError("not json")

        with patch("jks.agent.requests.post", return_value=FakeResponse()):
            client = HttpAgentClient("http://127.0.0.1:8787/chat", timeout=1.5)
            reply = client.send_message("hello", "conv-1")

        self.assertEqual(reply, AgentReply(text="plain response"))

    def test_http_client_wraps_request_failures(self):
        with patch("jks.agent.requests.post", side_effect=OSError("offline")):
            client = HttpAgentClient("http://127.0.0.1:8787/chat", timeout=1.5)

            with self.assertRaisesRegex(AgentProviderError, "agent request failed"):
                client.send_message("hello", "conv-1")

    def test_http_client_wraps_status_failures(self):
        class FakeResponse:
            def raise_for_status(self):
                raise RuntimeError("500")

            def json(self):
                return {"text": "ignored"}

        with patch("jks.agent.requests.post", return_value=FakeResponse()):
            client = HttpAgentClient("http://127.0.0.1:8787/chat")

            with self.assertRaisesRegex(AgentProviderError, "agent request failed"):
                client.send_message("hello", "conv-1")

    def test_http_client_rejects_empty_response_text(self):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"emotion": "thinking"}

        with patch("jks.agent.requests.post", return_value=FakeResponse()):
            client = HttpAgentClient("http://127.0.0.1:8787/chat")

            with self.assertRaisesRegex(AgentProviderError, "agent response did not contain text"):
                client.send_message("hello", "conv-1")

    def test_probe_contract_sends_probe_message_and_returns_reply(self):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"text": "probe ok", "emotion": "happy"}

        with patch("jks.agent.requests.post", return_value=FakeResponse()) as post:
            client = HttpAgentClient("http://127.0.0.1:8787/chat")
            reply = client.probe_contract()

        self.assertEqual(reply, AgentReply(text="probe ok", emotion="happy"))
        self.assertEqual(
            post.call_args.kwargs["json"],
            {"message": "JKS contract probe", "conversation_id": "contract-probe"},
        )

    def test_empty_endpoint_fails_before_posting(self):
        with patch("jks.agent.requests.post") as post:
            client = HttpAgentClient("")
            with self.assertRaises(RuntimeError):
                client.send_message("hello", "conv-1")

        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
