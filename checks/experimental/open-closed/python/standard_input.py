import sys


def paths_from_standard_input() -> list[str]:
    return [line for line in sys.stdin.read().split("\n") if line]
