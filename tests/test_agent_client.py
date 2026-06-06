import json
import subprocess
import unittest
from unittest.mock import patch

from jks.agent import (
    AgentProviderError,
    AgentReply,
    HttpAgentClient,
    SshHermesAgentClient,
    build_agent_client,
    parse_agent_reply,
)


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

    def test_parse_openai_like_choice_json_content_as_display_intent(self):
        reply = parse_agent_reply(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "text": "choice answer",
                                    "emotion": "surprised",
                                    "display_text": "WOW",
                                    "duration_ms": 1600,
                                    "intensity": "high",
                                }
                            ),
                        }
                    }
                ]
            }
        )

        self.assertEqual(
            reply,
            AgentReply(
                text="choice answer",
                emotion="surprised",
                display_text="WOW",
                duration_ms=1600,
                intensity="high",
            ),
        )

    def test_parse_openai_like_choice_json_content_with_nested_display_intent(self):
        reply = parse_agent_reply(
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "text": "choice answer",
                                    "display_intent": {
                                        "emotion": "thinking",
                                        "text": "WAIT",
                                        "duration_ms": 1400,
                                        "intensity": "normal",
                                    },
                                }
                            ),
                        }
                    }
                ]
            }
        )

        self.assertEqual(
            reply,
            AgentReply(
                text="choice answer",
                emotion="thinking",
                display_text="WAIT",
                duration_ms=1400,
                intensity="normal",
            ),
        )

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

    def test_http_client_uses_configured_openai_chat_model(self):
        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"choices": [{"message": {"content": "ok"}}]}

        with patch("jks.agent.requests.post", return_value=FakeResponse()) as post:
            client = HttpAgentClient(
                "http://127.0.0.1:8642/v1/chat/completions",
                model="gran-agent",
            )
            client.send_message("hello", "conv-1")

        self.assertEqual(post.call_args.kwargs["json"]["model"], "gran-agent")

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

    def test_ssh_hermes_client_invokes_sshpass_without_password_in_argv_and_parses_json(self):
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(
                {
                    "text": "hi from hermes",
                    "emotion": "happy",
                    "display_text": "HI",
                    "duration_ms": 900,
                    "intensity": "normal",
                }
            ),
            stderr="",
        )

        with patch("jks.agent.subprocess.run", return_value=completed) as run:
            client = SshHermesAgentClient(
                host="gran.example.com",
                user="jks",
                password="ssh-secret",
                command="/usr/local/bin/hermes",
                workdir="/srv/hermes",
                timeout=12.5,
            )
            reply = client.send_message("你好", "conv-1")

        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["sshpass", "-e", "ssh"])
        self.assertNotIn("ssh-secret", " ".join(command))
        self.assertEqual(run.call_args.kwargs["env"]["SSHPASS"], "ssh-secret")
        self.assertEqual(run.call_args.kwargs["timeout"], 12.5)
        self.assertIn("jks@gran.example.com", command)
        remote_command = command[-1]
        self.assertIn("cd /srv/hermes", remote_command)
        self.assertIn("/usr/local/bin/hermes", remote_command)
        self.assertIn("--continue jks-conv-1", remote_command)
        self.assertIn("-z", remote_command)
        self.assertIn("Return only compact JSON", remote_command)
        self.assertEqual(
            reply,
            AgentReply(
                text="hi from hermes",
                emotion="happy",
                display_text="HI",
                duration_ms=900,
                intensity="normal",
            ),
        )

    def test_ssh_hermes_client_uses_plain_ssh_when_password_is_absent(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="plain reply", stderr="")

        with patch("jks.agent.subprocess.run", return_value=completed) as run:
            client = SshHermesAgentClient(host="gran.local", user="")
            reply = client.send_message("hello", "conv/2")

        command = run.call_args.args[0]
        self.assertEqual(command[0], "ssh")
        self.assertNotIn("sshpass", command)
        self.assertNotIn("SSHPASS", run.call_args.kwargs["env"])
        self.assertIn("gran.local", command)
        self.assertIn("--continue jks-conv-2", command[-1])
        self.assertEqual(reply, AgentReply(text="plain reply"))

    def test_ssh_hermes_client_wraps_subprocess_failures(self):
        with patch(
            "jks.agent.subprocess.run",
            side_effect=subprocess.CalledProcessError(1, ["ssh"], stderr="denied"),
        ):
            client = SshHermesAgentClient(host="gran.local", password="ssh-secret")

            with self.assertRaisesRegex(AgentProviderError, "hermes ssh request failed"):
                client.send_message("hello", "conv-1")

    def test_ssh_hermes_client_retries_transient_subprocess_failure(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="retry reply", stderr="")

        with patch(
            "jks.agent.subprocess.run",
            side_effect=[
                subprocess.CalledProcessError(255, ["ssh"], stderr="connection reset"),
                completed,
            ],
        ) as run:
            client = SshHermesAgentClient(host="gran.local", user="")
            reply = client.send_message("hello", "conv-1")

        self.assertEqual(run.call_count, 2)
        self.assertEqual(reply, AgentReply(text="retry reply"))

    def test_build_agent_client_uses_longer_default_timeout_for_ssh_hermes(self):
        class Config:
            agent_endpoint = ""
            agent_token = ""
            agent_model = "hermes-agent"
            agent_host = "gran.example.com"
            agent_user = "jks"
            agent_ssh_password = ""
            agent_command = "/usr/local/bin/hermes"
            agent_workdir = "/srv/hermes"

        client = build_agent_client(Config())

        self.assertIsInstance(client, SshHermesAgentClient)
        self.assertGreaterEqual(client.timeout, 90.0)

    def test_build_agent_client_prefers_http_endpoint_over_ssh_host(self):
        class Config:
            agent_endpoint = "http://agent.local/chat"
            agent_token = "token"
            agent_model = "gran-agent"
            agent_host = "gran.example.com"
            agent_user = "jks"
            agent_ssh_password = "ssh-secret"
            agent_command = "/usr/local/bin/hermes"
            agent_workdir = "/srv/hermes"

        client = build_agent_client(Config(), timeout=7.0)

        self.assertIsInstance(client, HttpAgentClient)
        self.assertEqual(client.endpoint, "http://agent.local/chat")
        self.assertEqual(client.timeout, 7.0)

    def test_build_agent_client_uses_ssh_when_endpoint_is_missing_or_placeholder(self):
        class Config:
            agent_endpoint = "replace-with-agent-endpoint"
            agent_token = "replace-with-agent-token"
            agent_model = "hermes-agent"
            agent_host = "gran.example.com"
            agent_user = "jks"
            agent_ssh_password = "ssh-secret"
            agent_command = "/usr/local/bin/hermes"
            agent_workdir = "/srv/hermes"

        client = build_agent_client(Config(), timeout=7.0)

        self.assertIsInstance(client, SshHermesAgentClient)
        self.assertEqual(client.timeout, 7.0)
        self.assertEqual(client.host, "gran.example.com")

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
