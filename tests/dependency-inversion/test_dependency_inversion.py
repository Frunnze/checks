from dependency_inversion_support import (
    findings_for,
    repository_module,
    service_owning,
)

_REPOSITORY = repository_module()


def test_flags_a_service_constructing_its_repository() -> None:
    modules = {
        "repository.py": _REPOSITORY,
        "service.py": service_owning("UnitService", ["SqlUnitRepository"]),
    }

    assert findings_for(modules) == [
        (
            "service.py:2: UnitService constructs its own collaborators "
            "instead of receiving them: SqlUnitRepository"
        )
    ]


def test_allows_a_service_receiving_its_repository() -> None:
    service = (
        "class UnitService:\n"
        "    def __init__(self, repository):\n"
        "        self.repository = repository\n"
        "    def run(self):\n        return None\n"
    )

    assert findings_for(
        {"repository.py": _REPOSITORY, "service.py": service}
    ) == []


def test_allows_constructing_a_class_without_behavior() -> None:
    modules = {
        "unit.py": "class UnitName:\n    def __init__(self):\n        pass\n",
        "service.py": service_owning("UnitService", ["UnitName"]),
    }

    assert findings_for(modules) == []


def test_allows_constructing_an_unknown_third_party_class() -> None:
    modules = {"service.py": service_owning("UnitService", ["OpenAiClient"])}

    assert findings_for(modules) == []


def test_allows_a_factory_to_construct_collaborators() -> None:
    modules = {
        "repository.py": _REPOSITORY,
        "factory.py": service_owning("UnitFactory", ["SqlUnitRepository"]),
    }

    assert findings_for(modules) == []


def test_allows_the_application_factory_module_to_construct() -> None:
    modules = {
        "repository.py": _REPOSITORY,
        "app_factory.py": service_owning(
            "UnitService", ["SqlUnitRepository"]
        ),
    }

    assert findings_for(modules) == []


def test_reports_every_constructed_collaborator_sorted() -> None:
    modules = {
        "repository.py": _REPOSITORY,
        "sender.py": repository_module("EmailSender"),
        "service.py": service_owning(
            "UnitService", ["SqlUnitRepository", "EmailSender"]
        ),
    }

    assert findings_for(modules) == [
        (
            "service.py:2: UnitService constructs its own collaborators "
            "instead of receiving them: EmailSender, SqlUnitRepository"
        )
    ]


def test_allows_a_collaborator_built_into_a_local_variable() -> None:
    service = (
        "class UnitService:\n"
        "    def __init__(self):\n"
        "        repository = SqlUnitRepository()\n"
        "    def run(self):\n        return None\n"
    )

    assert findings_for(
        {"repository.py": _REPOSITORY, "service.py": service}
    ) == []
