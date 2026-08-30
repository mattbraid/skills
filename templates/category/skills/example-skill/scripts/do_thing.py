#!/usr/bin/env python3
"""Stub for a bundled script. Replace or delete.

Bundled scripts exist so a skill's repeatable mechanics live in code that runs
the same way every time, rather than being re-derived from the prose on each
invocation. Prefer the standard library: a plugin install does not run `pip`,
so a third-party import is a runtime failure on someone else's machine.
"""

import sys


def main(argv: list) -> int:
    if len(argv) != 2:
        print(f"usage: {sys.argv[0]} <input.json> <output.html>", file=sys.stderr)
        return 2
    src, dest = argv
    print(f"would read {src} and write {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
