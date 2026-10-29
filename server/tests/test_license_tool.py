"""The third-party license tool (change first-release): copyleft and unknown licenses need an
exception, and the generated sections replace only their markers."""

import importlib.util
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "licenses" / "generate.py"
spec = importlib.util.spec_from_file_location("license_tool", TOOL)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def package(name: str, license_: str):
    return tool.Package(name, "1.0", license_, "")


@pytest.mark.parametrize(
    ("license_", "refused"),
    [
        ("MIT", False),
        ("Apache-2.0 OR BSD-3-Clause", False),
        ("MPL-2.0", False),
        ("GPL-3.0-only", True),
        ("LGPL-2.1-or-later", True),
        ("AGPL-3.0", True),
        ("GNU General Public License v2 (GPLv2)", True),
        ("UNKNOWN", True),
    ],
)
def test_copyleft_and_unknown_licenses_are_refused(license_: str, refused: bool) -> None:
    assert bool(tool.problems([package("some-package", license_)], {})) is refused


def test_an_exception_allows_a_package() -> None:
    found = tool.problems(
        [package("Some_Package", "LGPL-3.0"), package("other", "GPL-2.0")],
        {"some-package": "dynamically loaded, reviewed"},
    )

    assert found == ["other 1.0: GPL-2.0"]


def test_only_the_marked_section_is_replaced() -> None:
    text = (
        "intro\n<!-- generated:server:start -->\nold\n<!-- generated:server:end -->\n"
        "<!-- generated:client:start -->\nkept\n<!-- generated:client:end -->\n"
    )

    replaced = tool.replace(text, "server", tool.table([package("fastapi", "MIT")]))

    assert "old" not in replaced and "kept" in replaced
    assert "| `fastapi` | 1.0 | MIT |  |" in replaced


def test_the_repository_file_is_current() -> None:
    """What CI's job "licenses" checks: the generated sections match the lockfiles."""
    if not (TOOL.parents[2] / "node_modules").is_dir():
        pytest.skip("the client's packages are not installed")
    assert tool.main(["--check"]) == 0
