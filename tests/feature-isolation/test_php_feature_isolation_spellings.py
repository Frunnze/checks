"""
PHP feature-isolation resolves a class however the package and the file
spell it: the psr-4 folder may have any name and may be listed as an
array, and a sibling class may be imported plainly, through a group use
or through an imported namespace. Domain: a package shop whose features
Cart and Billing meet in Shared\\Money, the psr-4 folder src or app as a
string or a list; and Cart reaching Billing\\Invoice in four spellings.
Oracle: metamorphic - every spelling gets the verdict of the plain `src/`
string mapping and the plain `use` statement.

Concrete inputs -> expected outputs:
- input: shop/composer.json {"autoload": {"psr-4": {"App\\\\": "app/"}}},
  source_directories = ["shop/app"], Cart and Billing both using
  App\\Shared\\Money
  output: expected exit 0, got exit 1 "shop/composer.json maps no
  namespace to src/".
- input: Cart.php with `use App\\Features\\{Billing\\Invoice};`
  output: expected exit 1 naming svc/src/Features/Cart/Cart.php:3, got
  exit 0 - the group member was read as App\\Features\\Cart\\Invoice.
- input: Cart.php with `use App\\Features\\Billing;` and
  `new Billing\\Invoice()` on line 4
  output: expected exit 1 naming svc/src/Features/Cart/Cart.php:4, got
  exit 0.
"""

from pathlib import Path

import pytest

from check_support import repository, run_configured, stage_file

MONEY = "<?php\nnamespace App\\Shared;\nfinal class Money {}\n"
MONEY_USER = (
    "<?php\nnamespace App\\Features\\{name};\n"
    "use App\\Shared\\Money;\n"
    "final class {name} {{ public function total(): Money "
    "{{ return new Money(); }} }}\n"
)
MAPPINGS = {
    "src_string": ("src", '"src/"'),
    "app_string": ("app", '"app/"'),
    "src_list": ("src", '["src/"]'),
}
INVOICE = "<?php\nnamespace App\\Features\\Billing;\nfinal class Invoice {}\n"
CART = (
    "<?php\nnamespace App\\Features\\Cart;\n{use_line}\n"
    "final class Cart {{ public function invoice(): {name} "
    "{{ return new {name}(); }} }}\n"
)
CROSSINGS = {
    "plain_use": ("use App\\Features\\Billing\\Invoice;", "Invoice", 3),
    "group_use": ("use App\\Features\\Billing\\{Invoice};", "Invoice", 3),
    "group_use_prefix": (
        "use App\\Features\\{Billing\\Invoice};",
        "Invoice",
        3,
    ),
    "namespace_alias": ("use App\\Features\\Billing;", "Billing\\Invoice", 4),
}


def _configuration(source_directory: str) -> str:
    return (
        f'source_directories = ["{source_directory}"]\nstable = "off"\n'
        '[checks.feature-isolation]\nwhen = "pre-commit"\n'
    )


@pytest.mark.parametrize("mapping", sorted(MAPPINGS))
def test_shared_money_passes_for_any_psr4_folder(
    tmp_path: Path, mapping: str
) -> None:
    folder, directories = MAPPINGS[mapping]
    repository(tmp_path)
    stage_file(
        tmp_path,
        "shop/composer.json",
        '{"autoload": {"psr-4": {"App\\\\": ' + directories + "}}}\n",
    )
    stage_file(tmp_path, f"shop/{folder}/Shared/Money.php", MONEY)

    for feature in ("Cart", "Billing"):
        stage_file(
            tmp_path,
            f"shop/{folder}/Features/{feature}/{feature}.php",
            MONEY_USER.format(name=feature),
        )

    finished = run_configured(
        tmp_path, _configuration(f"shop/{folder}"), "feature-isolation"
    )

    assert finished.returncode == 0, finished.stdout + finished.stderr


@pytest.mark.parametrize("spelling", sorted(CROSSINGS))
def test_a_sibling_class_is_a_crossing_in_every_spelling(
    tmp_path: Path, spelling: str
) -> None:
    use_line, name, line = CROSSINGS[spelling]
    repository(tmp_path)
    stage_file(
        tmp_path,
        "svc/composer.json",
        '{"autoload": {"psr-4": {"App\\\\": "src/"}}}\n',
    )
    stage_file(tmp_path, "svc/src/Features/Billing/Invoice.php", INVOICE)
    stage_file(
        tmp_path,
        "svc/src/Features/Cart/Cart.php",
        CART.format(use_line=use_line, name=name),
    )

    finished = run_configured(
        tmp_path, _configuration("svc/src"), "feature-isolation"
    )

    assert finished.returncode == 1, finished.stdout + finished.stderr
    assert f"svc/src/Features/Cart/Cart.php:{line}:" in finished.stderr
