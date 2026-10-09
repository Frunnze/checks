import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_WHITELIST = Path(__file__).with_name("whitelist.txt")
UNIT_KINDS = frozenset({"callable", "class", "module"})
ENTRY_FIELDS = frozenset({"path", "kind", "name", "entities", "reason"})
TEXT_FIELDS = ("path", "kind", "name", "reason")

type WhitelistKey = tuple[Path, str, str]
type Report = dict[str, Any]


@dataclass(frozen=True)
class WhitelistEntry:
    entities: tuple[str, ...]
    reason: str


type Whitelist = dict[WhitelistKey, WhitelistEntry]


def parse_entities(entities: object) -> tuple[str, ...]:
    if not isinstance(entities, list) or not entities:
        raise ValueError("entities must be a nonempty list")
    names: list[str] = []
    for entity in entities:
        if not isinstance(entity, str) or not entity.strip():
            raise ValueError("every entity must be a nonempty string")
        names.append(entity)
    if names != sorted(set(names)):
        raise ValueError("entities must be sorted and unique")
    return tuple(names)


def parse_entry(line: str) -> tuple[WhitelistKey, WhitelistEntry]:
    fields = json.loads(line)
    if not isinstance(fields, dict) or set(fields) != ENTRY_FIELDS:
        raise ValueError("expected path, kind, name, entities and reason")
    for field in TEXT_FIELDS:
        text = fields[field]
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{field} must be a nonempty string")
    if fields["kind"] not in UNIT_KINDS:
        raise ValueError(f"kind must be one of {sorted(UNIT_KINDS)}")
    entities = parse_entities(fields["entities"])
    key = (Path(fields["path"]).resolve(), fields["kind"], fields["name"])
    entry = WhitelistEntry(entities=entities, reason=fields["reason"].strip())
    return key, entry


def read_whitelist(path: Path) -> Whitelist:
    entries: Whitelist = {}
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    for line_number, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            key, entry = parse_entry(line)
            if key in entries:
                raise ValueError("duplicate finding")
        except ValueError as error:
            raise ValueError(
                f"invalid SRP whitelist {path}:{line_number}: {error}"
            ) from error
        entries[key] = entry
    return entries


def reject_stale_entries(reports: list[Report], entries: Whitelist) -> None:
    analyzed_paths: set[Path] = set()
    analyzed_units: set[WhitelistKey] = set()
    for report in reports:
        path = Path(report["path"]).resolve()
        analyzed_paths.add(path)
        for unit in report["units"]:
            analyzed_units.add((path, unit["kind"], unit["name"]))
    for key in entries:
        path, kind, name = key
        if path in analyzed_paths and key not in analyzed_units:
            raise ValueError(
                f"stale SRP whitelist entry {path} {kind} {name}: "
                "it matches no unit; remove or update it"
            )


def apply_whitelist(reports: list[Report], entries: Whitelist) -> Report:
    reject_stale_entries(reports, entries)
    count = 0
    for report in reports:
        path = Path(report["path"]).resolve()
        report["raw_coefficient"] = report["coefficient"]
        for unit in report["units"]:
            entry = entries.get((path, unit["kind"], unit["name"]))
            unit["whitelisted"] = False
            if entry is None or entry.entities != tuple(unit["entities"]):
                continue
            unit["whitelisted"] = True
            unit["whitelist_reason"] = entry.reason
            count += 1
        report["coefficient"] = max(
            (
                unit["coefficient"]
                for unit in report["units"]
                if not unit["whitelisted"]
            ),
            default=0.0,
        )
    return {
        "coefficient": max(
            (report["coefficient"] for report in reports), default=0.0
        ),
        "raw_coefficient": max(
            (report["raw_coefficient"] for report in reports), default=0.0
        ),
        "whitelisted_count": count,
    }
