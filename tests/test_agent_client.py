import json
import unittest
from unittest.mock import patch

from jks.agent import AgentReply, HttpAgentClient, parse_agent_reply


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

    def test_empty_endpoint_fails_before_posting(self):
        with patch("jks.agent.requests.post") as post:
            client = HttpAgentClient("")
            with self.assertRaises(RuntimeError):
                client.send_message("hello", "conv-1")

        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
