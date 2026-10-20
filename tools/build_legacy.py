"""Build the self-contained Python 2.7 plug-in; never import GIMP here."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build():
    core = (ROOT / "gimp-spot-heal/spot_core.py").read_text(encoding="utf-8")
    session = (ROOT / "legacy/session_210.py").read_text(encoding="utf-8")
    return "#!/usr/bin/env python2\n" + core + "\n\n" + session


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = ROOT / "legacy/spot-heal-210.py"
    if args.check:
        if target.read_text(encoding="utf-8") != build():
            raise SystemExit("Rebuild legacy plug-in: python tools/build_legacy.py")
    else:
        target.write_text(build(), encoding="utf-8")
