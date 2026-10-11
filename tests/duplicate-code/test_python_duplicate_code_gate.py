from pathlib import Path

from check_support import (
    link_toolkit_node_modules,
    repository,
    run_check,
    stage_file,
)

COPIED_LINES = "".join(
    f"    total = total * {step + 3} + values[{step}] - {step * 7}\n"
    for step in range(10)
)
UNIQUE_MODULES = 300
UNIQUE_LINES = 900


def _copied_function(name: str) -> str:
    return (
        f"def {name}(values: list[int]) -> int:\n"
        f"    total = 0\n{COPIED_LINES}    return total\n"
    )


def _unique_module(index: int) -> str:
    lines: list[str] = []

    for line in range(UNIQUE_LINES):
        value = index * 100003 + line * 7919
        lines.append(f"name_{index}_{line} = {value}\n")

    return "".join(lines)


def test_fails_on_a_copy_hidden_in_a_large_folder(tmp_path: Path) -> None:
    repository(tmp_path)
    link_toolkit_node_modules(tmp_path)
    stage_file(tmp_path, "user-service/src/first.py", _copied_function("first"))
    stage_file(
        tmp_path, "user-service/src/second.py", _copied_function("second")
    )

    for index in range(UNIQUE_MODULES):
        module = tmp_path / "user-service" / "src" / f"unique_{index}.py"
        _ = module.write_text(_unique_module(index), encoding="utf-8")

    finished = run_check(tmp_path, "duplicate-code")

    assert finished.returncode == 1
