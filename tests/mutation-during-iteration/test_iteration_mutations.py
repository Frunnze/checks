import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "mutation-during-iteration" / "python"
    / "iteration_mutations.py"
)
_PROBLEM = (
    " while a for loop iterates over it, so items are skipped or a"
    " RuntimeError is raised - loop over a copy such as"
)
_SHRINKING_CALLS = {
    "remove": "orders.remove(order)",
    "pop": "orders.pop()",
    "clear": "orders.clear()",
    "insert": "orders.insert(0, order)",
}
_COPIES = ("list(orders)", "orders[:]", "orders.copy()", "sorted(orders)")


def _report_for(tmp_path: Path, source: str) -> list[str]:
    module = tmp_path / "inventory.py"
    _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="inventory.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _finding(line_number: int, change: str, collection: str, copy: str) -> str:
    return (
        f"inventory.py:{line_number}: {change} changes {collection}"
        f"{_PROBLEM} {copy} or build a new one"
    )


def test_reports_a_list_shrunk_inside_its_own_loop(tmp_path: Path) -> None:
    source = (
        "def drop_cancelled(orders):\n"
        "    for order in orders:\n"
        "        if order.cancelled:\n"
        "            orders.remove(order)\n"
        "    return orders\n"
    )

    assert _report_for(tmp_path, source) == [
        _finding(4, "orders.remove()", "orders", "list(orders)")
    ]


def test_reports_a_dict_resized_through_its_views(tmp_path: Path) -> None:
    source = (
        "def expire(sessions, now):\n"
        "    for token, session in sessions.items():\n"
        "        if session.expires < now:\n"
        "            del sessions[token]\n"
        "    for token in sessions.keys():\n"
        "        sessions.pop(token)\n"
    )

    assert _report_for(tmp_path, source) == [
        _finding(4, "del sessions[token]", "sessions",
                 "list(sessions.items())"),
        _finding(6, "sessions.pop()", "sessions", "list(sessions.keys())"),
    ]


def test_passes_item_assignment_in_a_dict_loop(tmp_path: Path) -> None:
    source = (
        "def normalise(prices: dict[str, float], aliases: dict[str, str]):\n"
        "    for name in prices:\n"
        "        prices[name] = round(prices[name], 2)\n"
        "        prices[aliases[name]] = prices[name]\n"
        "        if name == 'total':\n"
        "            prices['total'] = 0.0\n"
    )

    assert _report_for(tmp_path, source) == []


def test_reports_a_set_attribute_and_a_counted_loop(tmp_path: Path) -> None:
    source = (
        "class Crawler:\n"
        "    def follow(self, links):\n"
        "        for link in self.seen:\n"
        "            self.seen.add(link + '/')\n"
        "        for position, link in enumerate(links):\n"
        "            links.pop(position)\n"
    )

    assert _report_for(tmp_path, source) == [
        _finding(4, "self.seen.add()", "self.seen", "list(self.seen)"),
        _finding(6, "links.pop()", "links", "list(enumerate(links))"),
    ]


def test_reports_growth_only_of_collections_that_lock(tmp_path: Path) -> None:
    source = (
        "from collections import deque\n"
        "def spread(start, tags: set[str]):\n"
        "    pending = deque([start])\n"
        "    for cell in pending:\n"
        "        pending.append(cell + 1)\n"
        "    for tag in tags:\n"
        "        tags |= {tag.upper()}\n"
        "    frontier = [start]\n"
        "    for cell in frontier:\n"
        "        frontier.append(cell + 1)\n"
        "        frontier += [cell + 2]\n"
    )

    assert _report_for(tmp_path, source) == [
        _finding(5, "pending.append()", "pending", "list(pending)"),
        _finding(7, "tags |= {tag.upper()}", "tags", "list(tags)"),
    ]


def test_reports_a_break_that_only_leaves_an_inner_loop(
    tmp_path: Path,
) -> None:
    source = (
        "def prune(groups, banned):\n"
        "    for group in groups:\n"
        "        for name in banned:\n"
        "            if name in group:\n"
        "                groups.remove(group)\n"
        "                break\n"
    )

    assert _report_for(tmp_path, source) == [
        _finding(5, "groups.remove()", "groups", "list(groups)")
    ]


def test_passes_a_change_that_ends_the_loop(tmp_path: Path) -> None:
    source = (
        "def take_first(orders, wanted):\n"
        "    for order in orders:\n"
        "        if order == wanted:\n"
        "            orders.remove(order)\n"
        "            print('taken')\n"
        "            break\n"
        "    for order in orders:\n"
        "        if order.urgent:\n"
        "            orders.remove(order)\n"
        "        return order\n"
        "    for order in orders:\n"
        "        if order.broken:\n"
        "            orders.clear()\n"
        "            raise ValueError(order)\n"
        "    else:\n"
        "        orders.clear()\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_copies_other_collections_and_callbacks(
    tmp_path: Path,
) -> None:
    source = (
        "def tidy(orders, archive, prices: dict[str, float]):\n"
        "    for order in list(orders):\n"
        "        orders.remove(order)\n"
        "    for name in list(prices):\n"
        "        del prices[name]\n"
        "    for order in orders:\n"
        "        archive.append(order)\n"
        "        archive.remove(order)\n"
        "        callbacks = [lambda: orders.clear()]\n"
        "        def later():\n"
        "            orders.clear()\n"
        "    for position, order in enumerate(orders):\n"
        "        orders[position] = order.strip()\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_containers_with_their_own_rules(tmp_path: Path) -> None:
    source = (
        "class Jar:\n"
        "    def purge(self, message):\n"
        "        for cookie in self:\n"
        "            self.clear(cookie.domain)\n"
        "        for header in message.keys():\n"
        "            message.replace_header(header, '')\n"
        "            del message[header]\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    method=st.sampled_from(sorted(_SHRINKING_CALLS)),
    copy=st.sampled_from(_COPIES),
)
def test_mutation_property_flags_only_the_live_loop(
    tmp_path: Path, method: str, copy: str
) -> None:
    call = _SHRINKING_CALLS[method]
    source = (
        "def sweep(orders):\n"
        f"    for order in {copy}:\n"
        f"        {call}\n"
        "    for order in orders:\n"
        f"        {call}\n"
    )

    report = _report_for(tmp_path, source)

    assert report == [
        _finding(5, f"orders.{method}()", "orders", "list(orders)")
    ]
