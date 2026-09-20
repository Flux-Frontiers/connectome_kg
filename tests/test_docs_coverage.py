"""Every ``connkg`` command has to appear on the documentation site.

0.5.0 shipped `connkg influence`, `connkg specs` and the answer grammar with
nothing about any of them on the site: the README had it all, the pages did
not, and Pages deployed green because a missing page is not a build error.
Nothing could have caught that, so this does.

The rule is deliberately weak -- the command's name has to appear somewhere in
``docs/`` -- because a strong one (every option, every example) would be
guesswork about what a page should say. A name that appears nowhere, though,
is a command the site does not admit exists.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from connectomekg.cli import cli

DOCS = Path(__file__).resolve().parent.parent / "docs"
MKDOCS = Path(__file__).resolve().parent.parent / "mkdocs.yml"

#: Pages written for readers of the repository rather than the site: mkdocs
#: never renders them, so they do not count as documenting anything.
NOT_PAGES = {"images/README.md"}


def _pages() -> list[Path]:
    """Every Markdown page mkdocs renders, API reference stubs included."""
    return [
        path
        for path in sorted(DOCS.rglob("*.md"))
        if path.relative_to(DOCS).as_posix() not in NOT_PAGES
    ]


@pytest.fixture(scope="module")
def site_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in _pages())


@pytest.fixture(scope="module")
def command_names() -> list[str]:
    return sorted(cli.commands)


def test_there_are_commands_to_check(command_names):
    """Guard the guard: an empty registry would make every assertion below pass."""
    assert len(command_names) > 10


def test_every_command_appears_on_the_site(command_names, site_text):
    missing = [name for name in command_names if f"connkg {name}" not in site_text]
    assert not missing, (
        f"not documented anywhere in docs/: {', '.join(missing)}. "
        "Add them to a page and list that page in mkdocs.yml's nav, or the "
        "site will not admit the commands exist."
    )


def test_every_page_is_in_the_nav():
    """An unreferenced page builds but is reachable only by guessing its URL.

    Matched as text rather than parsed as YAML on purpose: PyYAML is not a
    declared dependency here, it only arrives with the docs group, so parsing
    would import fine locally and fail in the test job that installs no extras.
    A nav entry is ``- Title: path.md``, so the path appearing verbatim is
    enough to tell a listed page from an orphaned one.
    """
    nav = MKDOCS.read_text(encoding="utf-8").split("nav:", 1)[-1]
    orphans = [
        path.relative_to(DOCS).as_posix()
        for path in _pages()
        if path.relative_to(DOCS).as_posix() not in nav
    ]
    assert not orphans, f"not in mkdocs.yml nav: {', '.join(orphans)}"
