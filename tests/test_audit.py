"""Each content check against the defect it exists for, and its look-alike.

Every recipe here is made up; each seeds one defect a person caught by hand in
a real book's review, beside a recipe that resembles it and is correct."""
from types import SimpleNamespace

import pytest

from family_cookbook import audit

META = """# {title}

- **Yield:** {yield_}
- **Prep time:** Not specified
- **Cook time:** {cook}
- **Temperature:** {temp}
"""


def findings(tmp_path, *, title="Test Cake", ingredients=("2 cups flour", "1 cup sugar", "2 eggs"),
             directions=("Mix flour, sugar, and eggs.", "Bake 30 minutes at 350°F."), notes=(),
             source="Test Cake\n2 cups flour, 1 cup sugar, 2 eggs. Mix. Bake 30 minutes at 350°.",
             cook="30 minutes", yield_="Not specified", temp="350°F", estimates=False):
    folder = tmp_path / "recipes" / "desserts" / "test-cake"
    folder.mkdir(parents=True, exist_ok=True)
    md = META.format(title=title, yield_=yield_, cook=cook, temp=temp)
    (folder / "recipe.md").write_text(md)
    r = SimpleNamespace(title=title, folder=folder, ingredients=list(ingredients), directions=list(directions),
                        notes=list(notes), prose=[], original_text=source)
    return [(f.severity, f.check) for f in audit.entry_findings(r, md, estimates)]


def test_a_correct_recipe_raises_nothing(tmp_path):
    assert findings(tmp_path) == []


def test_a_transcription_cut_off_at_a_page_break(tmp_path):
    cut = "Test Cake\n2 cups flour, 1 cup sugar, 2 eggs. Mix and bake at 350° for"
    assert ("error", "truncated") in findings(tmp_path, source=cut)


def test_a_last_step_that_stops_mid_sentence(tmp_path):
    assert ("error", "truncated") in findings(tmp_path, directions=("Mix flour, sugar, and eggs.", "Bake at 350°F and"))


@pytest.mark.parametrize("cook, flagged", [
    ("3 minutes", True),             # the first number in the text, not the bake
    ("33 minutes", False),           # every timed stage, summed
    ("30 minutes", False),           # the longest stage
    ("2 hours 30 minutes", True),    # a chill counted as cooking
])
def test_cook_time_against_the_stages(tmp_path, cook, flagged):
    steps = ("Boil sugar and water 3 minutes.", "Chill 2 hours.", "Bake 30 minutes at 350°F.")
    assert (("warning", "cook time") in findings(tmp_path, directions=steps, cook=cook)) is flagged


def test_spelled_out_times_are_read(tmp_path):
    steps = ("Mix flour, sugar, and eggs.", "Bake at 350°F for an hour and a half.")
    assert findings(tmp_path, directions=steps, cook="1 hour 30 minutes",
                    source="Test Cake\n2 cups flour, 1 cup sugar, 2 eggs. Bake an hour and a half at 350°.") == []


def test_a_temperature_the_directions_contradict(tmp_path):
    assert ("warning", "cook time") in findings(tmp_path, temp="375°F")


def test_a_yield_the_source_never_gives(tmp_path):
    assert ("warning", "invented") in findings(tmp_path, yield_="About 12 servings")


def test_a_book_that_keeps_estimates_accepts_about_yields_but_not_temperatures(tmp_path):
    assert ("warning", "invented") not in findings(tmp_path, yield_="About 12 servings", estimates=True)
    assert ("warning", "invented") in findings(tmp_path, yield_="12 servings", estimates=True)
    assert ("warning", "cook time") in findings(tmp_path, temp="About 375°F", estimates=True)


def test_an_amount_changed_from_the_source(tmp_path):
    assert ("warning", "invented") in findings(tmp_path, ingredients=("3 cups flour", "1 cup sugar", "2 eggs"))


def test_a_food_the_method_uses_but_the_list_does_not_name(tmp_path):
    steps = ("Mix flour, sugar, and eggs; fold in the walnuts.", "Bake 30 minutes at 350°F.")
    assert ("warning", "ingredients") in findings(tmp_path, directions=steps)


@pytest.mark.parametrize("step", [
    "Mash with a potato ricer, then mix flour, sugar, and eggs.",   # a tool
    "Bake 30 minutes at 350°F; the cake is done when it springs back.",  # the dish's own name
])
def test_words_that_only_look_like_missing_foods(tmp_path, step):
    assert findings(tmp_path, directions=("Mix flour, sugar, and eggs.", step)) == []


def test_a_family_line_dropped_from_the_recipe(tmp_path):
    source = ("Test Cake\n2 cups flour, 1 cup sugar, 2 eggs. Mix. Bake 30 minutes at 350°. "
              "Grandma hid these behind the flour bin so the grandchildren never found them.")
    assert ("warning", "dropped") in findings(tmp_path, source=source)
    kept = ("Grandma hid these behind the flour bin so the grandchildren never found them.",)
    assert findings(tmp_path, source=source, notes=kept) == []


@pytest.mark.parametrize("a, b, same", [
    ("Bea Lindqvist", "Beatrice Lindqvist", True),
    ("Bob Okafor", "Robert Okafor", True),
    ("Marla Quist", "Marlo Quist", True),
    ("Ann Lindqvist", "Ann", True),
    ("Ann Lindqvist", "Ann Okafor", False),
    ("Ann Lindqvist", "Bob Lindqvist", False),
])
def test_credits_that_name_one_person(a, b, same):
    assert bool(audit.same_person(a, b)) is same


@pytest.mark.parametrize("text, found", [
    ("Call me at (555) 867-5309 for the secret.", True),
    ("Write to bea@example.com.", True),
    ("Bring it to 1428 Elm Street.", True),
    ("3 Milky Way candy bars", False),
    ("Bake 350°F for 30-45 minutes; serves 8-10.", False),
])
def test_personal_data_in_printed_text(text, found):
    assert bool(audit.personal_data(text)) is found


def test_a_stage_inside_another_is_not_added_to_it(tmp_path):
    steps = ("Mix flour, sugar, and eggs.", "Bake for an hour, broiling for the last 30 minutes.")
    src = "Test Cake\n2 cups flour, 1 cup sugar, 2 eggs. Bake for an hour, broil the last half hour at 350°."
    assert ("warning", "cook time") in findings(tmp_path, directions=steps, source=src, cook="1 hour 30 minutes")
    assert ("warning", "cook time") not in findings(tmp_path, directions=steps, source=src, cook="1 hour")


def test_an_empty_ingredient_list_beside_a_method(tmp_path):
    assert ("error", "truncated") in findings(tmp_path, ingredients=())


def test_an_ingredient_line_that_says_what_the_source_does_not(tmp_path):
    src = "Test Cake\n2 cups flour, 1 cup sugar, 2 eggs, 1 1/2 teaspoon browned cinnamon. Bake 30 minutes at 350°."
    reworded = ("2 cups flour", "1 cup sugar", "2 eggs", "1 1/2 teaspoons ground cinnamon")
    faithful = ("2 cups flour", "1 cup sugar", "2 eggs", "1 1/2 teaspoons browned cinnamon")
    steps = ("Mix flour, sugar, eggs, and cinnamon.", "Bake 30 minutes at 350°F.")
    assert ("warning", "changed") in findings(tmp_path, ingredients=reworded, source=src, directions=steps)
    assert findings(tmp_path, ingredients=faithful, source=src, directions=steps) == []


def test_a_garbled_line_and_a_dangling_reference(tmp_path):
    garbled = ("2 cups flour > 1 cup sugar", "2 eggs")
    assert ("warning", "unclear") in findings(tmp_path, ingredients=garbled)
    steps = ("Mix the above ingredients.", "Bake 30 minutes at 350°F.")
    assert ("note", "reference") in findings(tmp_path, directions=steps)


def test_a_flavoring_does_not_list_the_food(tmp_path):
    listed = ("2 cups flour", "1 cup sugar", "2 eggs", "1 teaspoon almond extract")
    steps = ("Mix flour, sugar, eggs, and almond extract.", "Bake 30 minutes at 350°F; top with sliced almonds.")
    src = "Test Cake\n2 cups flour, 1 cup sugar, 2 eggs, 1 teaspoon almond extract. Bake 30 minutes at 350°. Top with sliced almonds."
    assert ("note", "ingredients") in findings(tmp_path, ingredients=listed, directions=steps, source=src)


def test_a_receipt_with_no_method_in_the_original_is_not_truncated(tmp_path):
    listed_only = "Molasses Cake\n1 cup butter, 1 cup sugar, 1 cup molasses, 4 eggs, 3 1/2 cups flour. MRS. ROE."
    got = findings(tmp_path, ingredients=("1 cup butter", "1 cup sugar", "1 cup molasses", "4 eggs", "3 1/2 cups flour"),
                   directions=(), source=listed_only, cook="Not specified", temp="Not specified")
    assert ("warning", "no method") in got and ("error", "truncated") not in got
    lost = "Test Cake\n2 cups flour, 1 cup sugar, 2 eggs. Mix well and bake 30 minutes at 350°."
    assert ("error", "truncated") in findings(tmp_path, directions=(), source=lost)


def test_molasses_and_sweetening_are_foods_the_method_uses(tmp_path):
    steps = ("Mix flour and eggs; stir in 1 teaspoon molasses.", "Sweeten to taste and bake 30 minutes at 350°F.")
    src = "Test Cake\n2 cups flour, 2 eggs. Mix, stir in 1 teaspoon molasses. Sweeten to taste, bake 30 minutes at 350°."
    findings(tmp_path, ingredients=("2 cups flour", "2 eggs"), directions=steps, source=src)
    md = (tmp_path / "recipes" / "desserts" / "test-cake" / "recipe.md").read_text()
    r = SimpleNamespace(title="Test Cake", folder=tmp_path / "recipes" / "desserts" / "test-cake",
                        ingredients=["2 cups flour", "2 eggs"], directions=list(steps), notes=[], prose=[],
                        original_text=src)
    missing = {f.message.split("uses ")[1].split(",")[0] for f in audit.entry_findings(r, md) if f.check == "ingredients"}
    assert missing == {"molasses", "sugar"}


@pytest.mark.parametrize("line, step", [
    ("1 quart milk, brought to a boil and poured over the potatoes", True),
    ("4 cups potatoes cut in 3/4 inch cubes", False),
    ("2 eggs, well beaten", False),
])
def test_a_step_inside_an_ingredient_line(tmp_path, line, step):
    src = ("Test Cake\n2 cups flour, 1 cup sugar, 2 eggs well beaten, 4 cups potatoes cut in 3/4 inch cubes, "
           "1 quart milk brought to a boil and poured over the potatoes. Mix. Bake 30 minutes at 350°.")
    got = findings(tmp_path, ingredients=("2 cups flour", "1 cup sugar", line), source=src)
    assert (("warning", "changed") in got) is step
