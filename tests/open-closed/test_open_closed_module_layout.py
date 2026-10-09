"""
Moving code between modules does not change what it does, so it must not
change the finder's verdict on a closed factory, and unrelated modules
must not change a module's own findings. Domain: 2-4 distinct exporter
names rendered into an abstract base, its subclasses and a factory that
selects between them, laid out either in one module or split in two.
Oracle: metamorphic - a semantics-preserving module split preserves the
verdict; adding an unrelated module preserves a module's own findings.

Concrete inputs -> expected outputs:
- input (single module, implementations ['csv', 'pdf']):
      class Exporter(ABC): ...
      class CsvExporter(Exporter): ...
      class PdfExporter(Exporter): ...
      class ExporterFactory:
          def create(self, fmt: str) -> Exporter:
              if fmt == 'csv':
                  return CsvExporter()
              return PdfExporter()
  output: reported -> ["one.py:21: create closes Exporter over concrete
  implementations: CsvExporter, PdfExporter"].
- input (shrunk falsifying example, now pinned as @example - the same
  code split so the factory imports the exporters):
      exporters.py: class Exporter(ABC) + CsvExporter + PdfExporter
      factory.py:   from exporters import ...  + ExporterFactory
  output: expected a report, got [].
"""

from hypothesis import example, given, settings
from hypothesis import strategies as st

from open_closed_finder_support import (
    IDENTIFIERS,
    abstraction_module,
    equality_chain,
    factory_body,
    findings_for,
    subject_names,
    variant_sets,
)

_IMPLEMENTATIONS = ["csv", "pdf"]
_VARIANTS = ["deck", "file", "note"]
_SUBJECT = "a_kind"
implementation_sets = st.lists(
    IDENTIFIERS, min_size=2, max_size=4, unique=True
).map(sorted)


@given(implementations=implementation_sets)
@example(implementations=_IMPLEMENTATIONS)
@settings(max_examples=100, deadline=None)
def test_closed_factory_property_survives_a_module_split(
    implementations: list[str],
) -> None:
    together = abstraction_module(implementations) + factory_body(
        implementations
    )
    single = findings_for({"one.py": together})
    split = findings_for(
        {
            "exporters.py": abstraction_module(implementations),
            "factory.py": (
                "from exporters import Exporter\n\n\n"
                + factory_body(implementations)
            ),
        }
    )

    assert not single or split


@given(
    subject=subject_names,
    variants=variant_sets,
    implementations=implementation_sets,
)
@example(
    subject=_SUBJECT,
    variants=_VARIANTS,
    implementations=_IMPLEMENTATIONS,
)
@settings(max_examples=100, deadline=None)
def test_variant_dispatch_property_ignores_unrelated_modules(
    subject: str, variants: list[str], implementations: list[str]
) -> None:
    dispatch = equality_chain(subject, variants)
    alone = findings_for({"route.py": dispatch})
    accompanied = [
        report
        for report in findings_for(
            {
                "route.py": dispatch,
                "unrelated.py": abstraction_module(implementations),
            }
        )
        if report.startswith("route.py:")
    ]

    assert accompanied == alone
