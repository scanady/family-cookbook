"""The example book carries four defects on purpose, so `cookbook review` and the
book report have something real to show. This keeps them there, and keeps the
audit catching them: a change that loses one, or a fix that removes one, fails
here. The list is in docs/COMMANDS.md ("The example book")."""
import re
import subprocess
import sys
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "fannie-farmer-1896"

SEEDED = {
    ("cook time", "Fish Chowder"),            # Cook time 20 minutes: the first number in the text, not the 45
    ("invented", "Boston Baked Beans"),       # Yield "About 8 servings": the book never says
    ("ingredients", "Indian Pudding"),        # ginger left out of the list
    ("invented", "Strawberry Short Cake"),    # 3 teaspoons baking powder where the source says 4
}


def test_the_example_book_shows_exactly_its_seeded_defects():
    run = subprocess.run(
        [sys.executable, "-c", "import sys; from family_cookbook.cli import main; sys.exit(main(sys.argv[1:]))",
         "audit", "--book", str(EXAMPLE)],
        capture_output=True, text=True, check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr  # warnings only: CI builds this book
    found = {(m[1].strip(), m[2]) for m in re.finditer(r"^(?:ERROR|WARNING)\s+(.+?)\s{2,}(.+?): ", run.stdout, re.M)}
    assert found == SEEDED
