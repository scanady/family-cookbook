"""What `cookbook init` leaves for the family to fill in: lint calls every
placeholder an error, press stops on them before building anything, and the
AI key's example file is the one .env file git keeps.

Each test runs the real command in a fresh process: the layout modules read
the book root once, when they are first imported."""
import shutil
import subprocess
import sys

import pytest

RECIPE = """# Skillet Cornbread

*Ruth Baker*

## Ingredients

- 1 cup cornmeal
- 1 cup buttermilk

## Directions

1. Stir together and bake at 425°F until golden, about 20 minutes.
"""

WRITTEN = {
    "book/sections/matter-dedication/page.md": "*For everyone who asked for the recipe.*\n",
    "book/sections/matter-closing-message/page.md": "*Add your own.*\n",
    "book/sections/mains/page.md": "*Supper, most nights.*\n",
    "book/sections/kitchen-tips/page.md": "*What the kitchen taught us.*\n",
    "book/cover.md": "# Back Cover\n\nRecipes from the Baker kitchen.\n\n*The Bakers*\n",
}


def cookbook(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", "import sys; from family_cookbook.cli import main; sys.exit(main())", *args],
        capture_output=True, text=True,
    )


@pytest.fixture
def book(tmp_path):
    """A book fresh from `cookbook init`, its placeholders untouched, with one recipe."""
    result = cookbook("init", "--book", str(tmp_path), "--categories", "mains",
                      "--sections", "kitchen-tips", "--title", "Test Kitchen")
    assert result.returncode == 0, result.stderr
    recipe = tmp_path / "book" / "recipes" / "mains" / "skillet-cornbread" / "recipe.md"
    recipe.parent.mkdir(parents=True)
    recipe.write_text(RECIPE, encoding="utf-8")
    return tmp_path


def placeholder_files(output: str) -> set[str]:
    return {line.split()[1].split(":")[0] for line in output.splitlines()
            if line.startswith("ERROR") and "placeholder" in line}


def test_lint_flags_every_placeholder_until_it_is_written(book):
    result = cookbook("lint", "--book", str(book))
    assert result.returncode == 1
    assert placeholder_files(result.stdout) == {"book/book.yaml", *WRITTEN}

    for rel, text in WRITTEN.items():
        (book / rel).write_text(text, encoding="utf-8")
    config = book / "book" / "book.yaml"
    config.write_text(config.read_text(encoding="utf-8").replace("TODO: the family name", "The Bakers"),
                      encoding="utf-8")
    result = cookbook("lint", "--book", str(book))
    assert result.returncode == 0, result.stdout
    assert "placeholder" not in result.stdout


def test_press_stops_on_lint_errors_before_building(book):
    result = cookbook("press", "--book", str(book))
    assert result.returncode == 1
    assert "placeholder" in result.stdout
    assert "== cookbook fit" not in result.stdout
    assert not (book / "draft").exists()


@pytest.mark.skipif(not shutil.which("git"), reason="needs git")
def test_init_writes_an_env_example_git_keeps(book):
    assert "GEMINI_API_KEY=" in (book / ".env.example").read_text(encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=book, check=True)
    ignored = lambda name: subprocess.run(["git", "check-ignore", "-q", name], cwd=book).returncode == 0
    assert not ignored(".env.example")
    assert ignored(".env")
