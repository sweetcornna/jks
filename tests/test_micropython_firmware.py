import ast
from pathlib import Path
import unittest


FIRMWARE = Path("firmware/micropython/main.py")


class MicroPythonFirmwareTests(unittest.TestCase):
    def test_main_py_is_valid_python_syntax(self):
        ast.parse(FIRMWARE.read_text())

    def test_firmware_defines_frames_for_all_base_emotions(self):
        frames = _literal_assignment("FACE_FRAMES")
        for emotion in (
            "neutral",
            "happy",
            "thinking",
            "speaking",
            "listening",
            "surprised",
            "sleepy",
            "sad",
            "angry",
            "error",
        ):
            with self.subTest(emotion=emotion):
                self.assertIn(emotion, frames)
                self.assertGreaterEqual(len(frames[emotion]), 2)
                self.assertTrue(all(len(frame) == 6 for frame in frames[emotion]))

    def test_core_firmware_animations_have_lively_motion_offsets(self):
        frames = _literal_assignment("FACE_FRAMES")

        for emotion in ("happy", "thinking", "speaking", "listening", "surprised"):
            with self.subTest(emotion=emotion):
                emotion_frames = frames[emotion]
                self.assertGreaterEqual(len(emotion_frames), 4)
                self.assertTrue(any(frame[4] != 0 or frame[5] != 0 for frame in emotion_frames))
                self.assertGreaterEqual(len({frame[3] for frame in emotion_frames}), 2)

    def test_firmware_speaking_animation_uses_multiple_mouth_shapes(self):
        frames = _literal_assignment("FACE_FRAMES")

        self.assertGreaterEqual(len({frame[2] for frame in frames["speaking"]}), 3)
        self.assertTrue(any(frame[4] < 0 for frame in frames["error"]))
        self.assertTrue(any(frame[4] > 0 for frame in frames["error"]))

    def test_firmware_accepts_full_display_intent_fields(self):
        source = FIRMWARE.read_text()

        self.assertIn("duration_ms", source)
        self.assertIn("intensity", source)
        self.assertIn("display_text", source)

    def test_firmware_accepts_custom_face_pattern_fields(self):
        source = FIRMWARE.read_text()

        self.assertIn("draw_custom_face", source)
        self.assertIn('data.get("left_eye"', source)
        self.assertIn('data.get("right_eye"', source)
        self.assertIn('data.get("mouth"', source)
        self.assertIn('data.get("x_offset"', source)
        self.assertIn('data.get("y_offset"', source)

    def test_firmware_custom_face_supports_continuous_motion(self):
        source = FIRMWARE.read_text()
        motions = _literal_assignment("MOTIONS")

        self.assertGreaterEqual(set(motions), {"still", "blink", "bob", "shake", "talk", "bounce"})
        self.assertIn('data.get("motion"', source)
        self.assertIn("custom_motion_frame", source)
        self.assertIn("active_animation", source)

    def test_firmware_polls_serial_input_while_animating_between_commands(self):
        source = FIRMWARE.read_text()

        self.assertIn("select.poll", source)
        self.assertIn("def input_ready", source)
        self.assertIn("def animate_tick", source)
        self.assertIn("if input_ready():", source)
        self.assertIn("animate_tick()", source)
        self.assertNotIn("while True:\n    line = sys.stdin.readline()\n    handle(line)\n    time.sleep_ms(10)", source)

    def test_firmware_keeps_verified_sh1106_hardware_baseline(self):
        tree = ast.parse(FIRMWARE.read_text())
        constants = _literal_assignments()
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "SH1106"
        ]

        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(_node_value(call.args[0], constants), 128)
        self.assertEqual(_node_value(call.args[1], constants), 64)
        self.assertEqual(_node_value(call.args[3], constants), 0x3C)
        self.assertEqual(
            {keyword.arg: _node_value(keyword.value, constants) for keyword in call.keywords},
            {"col_offset": 2},
        )


def _literal_assignment(name):
    assignments = _literal_assignments()
    if name in assignments:
        return assignments[name]
    raise AssertionError(f"{name} assignment not found")


def _literal_assignments():
    tree = ast.parse(FIRMWARE.read_text())
    assignments = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    try:
                        assignments[target.id] = ast.literal_eval(node.value)
                    except (ValueError, TypeError):
                        pass
    return assignments


def _node_value(node, constants):
    if isinstance(node, ast.Name):
        return constants[node.id]
    return ast.literal_eval(node)


if __name__ == "__main__":
    unittest.main()
