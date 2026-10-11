from pathlib import Path

import pytest

from check_support import (
    link_toolkit_node_modules,
    repository,
    run_check,
    stage_file,
)


@pytest.mark.parametrize(
    "silencer",
    [
        "/* eslint-disable @typescript-eslint/no-explicit-any */\n",
        '/* eslint @typescript-eslint/no-explicit-any: "off" */\n',
        "/*eslint @typescript-eslint/no-explicit-any: 0*/\n",
    ],
)
def test_fails_on_a_silenced_lint_rule(tmp_path: Path, silencer: str) -> None:
    repository(tmp_path)
    link_toolkit_node_modules(tmp_path)
    stage_file(
        tmp_path,
        "ui-service/src/value.ts",
        f"{silencer}export const value: any = 1;\n",
    )

    finished = run_check(tmp_path, "strict-typing")

    assert finished.returncode == 1
    assert "ui-service/src/value.ts" in finished.stderr
