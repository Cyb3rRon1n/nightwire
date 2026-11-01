import re
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
PAGE = REPO / "tools" / "character_creator.html"


@pytest.fixture
def page():
    return PAGE.read_text()


def test_page_ships_as_package_data():
    assert PAGE.is_file()
    config = tomllib.loads((REPO / "pyproject.toml").read_text())
    assert "character_creator.html" in config["tool"]["setuptools"]["package-data"]["tools"]


def test_page_depends_on_nothing_outside_itself(page):
    assert "window.claude" not in page
    assert not re.search(r"""\bsrc\s*=\s*["']?(https?:)?//""", page)
    assert not re.search(r"""href\s*=\s*["']?(https?:)?//""", page)
    assert "http://" not in page and "https://" not in page
    assert "@import" not in page and "<script src" not in page and "<link" not in page


def test_player_values_never_become_markup(page):
    for risky in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert risky not in page


def test_nothing_accepts_an_upload(page):
    assert 'type="file"' not in page and "FormData" not in page and "'file'" not in page and '"file"' not in page


@pytest.mark.parametrize("path", ["/create/api", "/options", "/characters", "/answers", "/generate", "/vary", "/pick", "/favourite",
                                  "/lock", "/sheet", "/retry", "/image/", "/owner/", "/accept", "/decline"])
def test_every_api_path_is_used(page, path):
    assert path in page


def test_page_keeps_the_shared_rules(page):
    for rule in ("#07060d", "#ff4fa3", "#3fd5ff", ":focus-visible", 'name="viewport"', 'content="no-referrer"', "visibilitychange"):
        assert rule in page
    assert "confirm(" not in page and "alert(" not in page   # confirmations happen on the page
    assert "suggest" in page and "/create/owner/" in page and "/create/c/" in page
