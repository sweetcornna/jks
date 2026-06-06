from __future__ import annotations

import json
import sys
from typing import Optional, Sequence, TextIO

from jks.config import load_config
from jks.preflight import analyze_config


def main(argv: Optional[Sequence[str]] = None, stdout: TextIO = sys.stdout) -> int:
    try:
        summary = analyze_config(load_config())
    except Exception as exc:
        summary = {"ok": False, "errors": [{"error": "config", "message": str(exc)}]}
    stdout.write(json.dumps(summary, ensure_ascii=False, separators=(",", ":")) + "\n")
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
