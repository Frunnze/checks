"""
Enqueueing a Celery task is a queue effect: `delay` and `apply_async` are
catalogued queue operations, and Celery's documented way to enqueue is to
call them on a project function decorated with `@shared_task` or
`@app.task`. Domain: a send_report task declared with either decorator,
in its own module or beside the caller, enqueued with delay or
apply_async by a unit that also posts over HTTP. Oracle: the catalogue
contract - the unit reaches network and queue, like the tested
`celery.Celery('jobs').send_task(...)` spelling.

Concrete inputs -> expected outputs:
- input:
      tasks.py: from celery import shared_task
                @shared_task
                def send_report(url):
                    return url
      views.py: import httpx
                from tasks import send_report
                def publish(url):
                    httpx.post(url)
                    send_report.delay(url)
  output: expected <module>.publish -> ["network", "queue"], got
  ["network"] and a passing gate - the call resolved to the project
  function, never to a name under celery.
- input: a plain project function `def helper(url): ...` called as
  `helper(url)` next to httpx.post
  output: ["network"] - only a delay or apply_async call enqueues.
"""

import tempfile
from pathlib import Path

from check_support import HYPOTHESIS_SETTINGS
from hypothesis import example, given
from hypothesis import strategies as st
from srp_support import run_project, unit_named

TASKS = {
    "shared_task": (
        "from celery import shared_task\n\n\n@shared_task\n"
        "def send_report(url):\n    return url\n"
    ),
    "app_task": (
        "from celery import Celery\n\napp = Celery('jobs')\n\n\n@app.task\n"
        "def send_report(url):\n    return url\n"
    ),
}
ENQUEUE_CALLS = {
    "delay": "send_report.delay(url)",
    "apply_async": "send_report.apply_async(args=[url])",
}
PUBLISH = "def publish(url):\n    httpx.post(url)\n    {enqueue}\n"


def _publisher_entities(task: str, enqueue: str, same_file: bool) -> list:
    publish = PUBLISH.format(enqueue=ENQUEUE_CALLS[enqueue])

    if same_file:
        files = {"views.py": f"import httpx\n{TASKS[task]}\n\n{publish}"}
    else:
        files = {
            "tasks.py": TASKS[task],
            "views.py": (
                f"import httpx\nfrom tasks import send_report\n\n\n{publish}"
            ),
        }

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)

        for name, source in files.items():
            _ = (root / name).write_text(source, encoding="utf-8")

        report = run_project(root)

    return unit_named(report, "<module>.publish")["entities"]


@given(
    task=st.sampled_from(sorted(TASKS)),
    enqueue=st.sampled_from(sorted(ENQUEUE_CALLS)),
    same_file=st.booleans(),
)
@example(task="shared_task", enqueue="delay", same_file=False)
@example(task="app_task", enqueue="apply_async", same_file=True)
@HYPOTHESIS_SETTINGS
def test_enqueue_property_a_project_task_reaches_the_queue(
    task: str, enqueue: str, same_file: bool
) -> None:
    entities = _publisher_entities(task, enqueue, same_file)

    assert entities == ["network", "queue"]


def test_a_plain_project_call_is_not_a_queue() -> None:
    views = (
        "import httpx\n\n\ndef helper(url):\n    return url\n\n\n"
        "def publish(url):\n    httpx.post(url)\n    helper(url)\n"
    )

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _ = (root / "views.py").write_text(views, encoding="utf-8")
        report = run_project(root)

    assert unit_named(report, "<module>.publish")["entities"] == ["network"]
