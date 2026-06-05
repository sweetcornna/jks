from machine import Pin, I2C
import sys
import time
from ssd1306_min import SH1106, blink_probe


SDA = 4
SCL = 5
ADDR = 0x3C
WIDTH = 128
HEIGHT = 64
VISIBLE_X = 30
VISIBLE_Y = 12


i2c = I2C(0, sda=Pin(SDA), scl=Pin(SCL), freq=100000)
display = SH1106(WIDTH, HEIGHT, i2c, ADDR, col_offset=2)
current_emotion = "happy"
current_text = "JKS READY"


def ack(status, detail):
    print('{"status":"%s","detail":"%s"}' % (status, detail.replace('"', "")))


def face_for(emotion):
    faces = {
        "happy": "^_^",
        "smile": "^_^",
        "joy": "^_^",
        "sad": "T_T",
        "angry": ">_<",
        "surprised": "O_O",
        "wow": "O_O",
        "thinking": "?_?",
        "think": "?_?",
        "speaking": "^o^",
        "talk": "^o^",
        "sleepy": "-_-",
        "sleep": "-_-",
        "neutral": "._.",
    }
    return faces.get(emotion, "._.")


def clean(text, limit=14):
    out = ""
    for ch in str(text):
        if " " <= ch <= "~":
            out += ch
        if len(out) >= limit:
            break
    return out


def draw(emotion=None, text=None):
    global current_emotion, current_text
    if emotion is not None:
        current_emotion = emotion
    if text is not None:
        current_text = text

    display.fill(0)
    display.rect(0, 0, WIDTH, HEIGHT, 1)
    display.text(face_for(current_emotion), 48, 18, 1)
    display.text(clean(current_text, 16), 8, 40, 1)
    display.show()


def clear():
    display.fill(0)
    display.show()


def probe():
    for _ in range(2):
        display.fill(1)
        display.show()
        time.sleep_ms(300)
        display.fill(0)
        display.show()
        time.sleep_ms(200)

    display.fill(0)
    display.rect(0, 0, WIDTH, HEIGHT, 1)
    display.rect(VISIBLE_X, VISIBLE_Y, 72, 40, 1)
    display.fill_rect(0, 0, 12, 12, 1)
    display.fill_rect(WIDTH - 12, 0, 12, 12, 1)
    display.fill_rect(0, HEIGHT - 12, 12, 12, 1)
    display.fill_rect(WIDTH - 12, HEIGHT - 12, 12, 12, 1)
    display.text("JKS", VISIBLE_X + 8, VISIBLE_Y + 8, 1)
    display.text("OLED", VISIBLE_X + 8, VISIBLE_Y + 24, 1)
    display.show()


def handle(line):
    line = line.strip()
    if not line:
        return
    if line.lower() == "clear":
        clear()
        ack("ok", "clear")
        return
    if line.lower() == "probe":
        probe()
        ack("ok", "probe")
        return
    if line.startswith("{"):
        try:
            import json

            data = json.loads(line)
            cmd = data.get("cmd") or data.get("type")
            if cmd == "clear":
                clear()
                ack("ok", "clear")
            elif cmd == "probe":
                probe()
                ack("ok", "probe")
            elif cmd == "text":
                draw("neutral", data.get("text", ""))
                ack("ok", "text")
            elif cmd in ("emotion", "face"):
                name = data.get("name", "neutral")
                draw(name, data.get("text", name))
                ack("ok", name)
            else:
                ack("error", "unknown")
        except Exception as exc:
            ack("error", str(exc))
        return
    draw("neutral", line)
    ack("ok", "text")


def boot():
    print("JKS MicroPython OLED controller boot")
    print("i2c scan", [hex(x) for x in i2c.scan()])
    blink_probe(display)
    draw(current_emotion, current_text)
    ack("ok", "boot")


boot()

while True:
    line = sys.stdin.readline()
    handle(line)
    time.sleep_ms(10)
