"""Create the standalone GIMP 2.10 plug-in from its two source components."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build():
    return ("#!/usr/bin/env python2\n" +
            (ROOT / "src/mask_core.py").read_text(encoding="utf-8") + "\n\n" +
            (ROOT / "src/session_210.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = ROOT / "legacy/spot-heal-mask-210.py"
    if args.check:
        if target.read_text(encoding="utf-8") != build():
            raise SystemExit("Run python tools/build_plugin.py")
    else:
        target.write_text(build(), encoding="utf-8")
