"""`cookbook audit`: the content checks, and one report for the whole book.

Each check catches a defect a person found by hand in a real book's review:

- truncated      a transcription or method that stops mid-sentence, or a page
                 number left inside a transcription where a page break was joined
- cook time      Cook time that no stated duration supports, the "first number
                 in the text" error; Temperature that the directions contradict
- invented       a Yield, Prep time, or Temperature figure the source never states
- ingredients    a food the method uses that the ingredient list does not name
- dropped        a sentence of the source (a tip, a story, the family's voice)
                 that is nowhere in the recipe
- same cook      credits that probably name one person (Bea / Beatrice, Marla /
                 Marlo), which the contributors page would list twice
- personal data  a phone number, email address, or street address in printed text

All are read from the recipes as the renderer parses them, so a finding is
about what prints. They run offline and cost nothing. The report adds what the
engine already flags: lint, the photo rules and resolution `cookbook fit`
reports, and, with --check, `cookbook check`'s overflow and type-size failures.

Writes draft/book-report.html: everything flagged, errors first, each entry
with its page number and a link to that page in the screen draft.
"""
from __future__ import annotations

import html
import re
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

from . import config

SEVERITIES = ("error", "warning", "note")


@dataclass(frozen=True)
class Finding:
    severity: str   # error | warning | note
    check: str      # the check's short name, as in the module docstring
    entry: str      # "recipes/desserts/carrot-cake", or "" for the book as a whole
    message: str


# ---- reading text --------------------------------------------------------------

UNICODE_FRACTIONS = {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3", "⅛": "1/8"}
WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20,
    "thirty": 30, "forty": 40, "forty-five": 45, "fifty": 50, "sixty": 60, "ninety": 90,
}
_NUM = r"\d+(?:\.\d+)?|" + "|".join(sorted(WORD_NUMBERS, key=len, reverse=True))
DURATION = re.compile(
    rf"\b(?P<a>{_NUM})(?:\s*(?:-|–|to|or)\s*(?P<b>{_NUM}))?\s*(?P<unit>minutes?|mins?\b|hours?|hrs?\b)",
    re.I,
)
# Stages that are not cooking: a chill, a rest, a rise, a soak, a marinade.
NOT_COOKING = re.compile(r"chill|refrigerat|fridge|freez|\brest|stand|\bcool|soak|marinat|overnight|\brise|let set|"
                         r"\bsit\b|\bleave|turn(?:ed)? off|oven off", re.I)
# Mixing is not cooking either, unless the sentence also heats ("boil, stirring").
MIXING = re.compile(r"\bbeat|\bstir|\bmix|whisk|knead|\bwhip", re.I)
HEAT = re.compile(r"\bbake|\bboil|simmer|\bcook|\bfry|fries|roast|broil|saut|\bbrown|\bheat|oven|microwave|grill|"
                  r"steam|toast|\bsear|thicken|\bmelt", re.I)
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60}
UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
TEMPERATURE = re.compile(r"\b([2-5]\d\d)\s*(?:°|º|\*|degrees?|deg\b)", re.I)
OVEN_NUMBER = re.compile(r"\b(?:at|to|oven|bake|heat|preheat)\s+(?:\w+\s+){0,2}?([2-5]\d\d)\b(?!\s*(?:g|ml|minutes?|hours?))", re.I)


def _dec(value: float) -> str:
    return f"{value:g}"


def _plain(text: str) -> str:
    """Every amount as a decimal: "½", "1/2", "1 1/2", "1-1/4", "thirty-five",
    "three and one-half hours", "an hour and a half", "half an hour"."""
    for glyph, frac in UNICODE_FRACTIONS.items():
        text = re.sub(rf"(\d)\s*{glyph}", rf"\1 {frac}", text).replace(glyph, frac)
    text = re.sub(r"(\d+)[\s-]+(\d+)/(\d+)", lambda m: _dec(int(m[1]) + int(m[2]) / int(m[3])), text)
    text = re.sub(r"(?<![\d.])(\d+)/(\d+)", lambda m: _dec(int(m[1]) / int(m[2])), text)
    text = re.sub(rf"\b({'|'.join(TENS)})-({'|'.join(UNITS)})\b",
                  lambda m: str(TENS[m[1].lower()] + UNITS[m[2].lower()]), text, flags=re.I)
    number = rf"(\d+(?:\.\d+)?|{'|'.join(WORD_NUMBERS)})"
    # "an hour and a half", "2 hours and a half"
    text = re.sub(rf"\b{number}\s+(hours?|minutes?)\s+and\s+a\s+half\b",
                  lambda m: f"{_dec(_number(m[1]) + .5)} {m[2]}", text, flags=re.I)
    # "three and one-half hours", "1 and a half hours", "one and a quarter hours"
    for word, extra in (("half", .5), ("quarter", .25), ("three-quarters?", .75)):
        text = re.sub(rf"\b{number}\s+and\s+(?:one-|a\s+)?{word}\s+(hours?|minutes?)",
                      lambda m, e=extra: f"{_dec(_number(m[1]) + e)} {m[2]}", text, flags=re.I)
    text = re.sub(r"\bhalf\s+(?:an?\s+)?hour\b", "30 minutes", text, flags=re.I)
    return text


def _number(token: str) -> float:
    return float(WORD_NUMBERS.get(token.lower(), token))


def durations(text: str) -> list[tuple[float, float, str]]:
    """Every duration stated in text, in minutes: (low, high, kind). The kind is
    "cook"; "rest" for a chill, a stand, a marinade, or mixing; or "within" for
    a stage inside another ("broil for the last half hour"), never added to it."""
    found = []
    plain = _plain(text)
    for sentence in re.split(r"(?<=[.!?;])\s+|\n", plain):
        resting = NOT_COOKING.search(sentence) or (MIXING.search(sentence) and not HEAT.search(sentence))
        last_end = -1
        for m in DURATION.finditer(sentence):
            before = sentence[: m.start()]
            if re.search(r"\bevery\s*$", before, re.I):
                continue  # "baste every fifteen minutes" is an interval, not a stage
            kind = "within" if re.search(r"\b(?:last|final|remaining)\s*$", before, re.I) else \
                "rest" if resting else "cook"
            scale = 60 if m.group("unit").lower().startswith("h") else 1
            if re.match(r"\s*(?:on\s+)?(?:each|per)\s+side", sentence[m.end():], re.I):
                scale *= 2  # "5 to 6 minutes on each side"
            a = _number(m.group("a")) * scale
            b = _number(m.group("b")) * scale if m.group("b") else a
            if found and last_end >= 0 and re.fullmatch(r"\s*(?:to|or|-|–)\s*", sentence[last_end:m.start()]):
                # "50 minutes to 1 hour": one range, not two stages
                found[-1] = (found[-1][0], b, found[-1][2])
            else:
                found.append((a, b, kind))
            last_end = m.end()
    return found


def meta_minutes(value: str) -> tuple[float, float] | None:
    """A Cook time value ("1 hour 10 minutes", "About 10 to 12 minutes") as (low, high)."""
    if not re.search(r"\d", value):
        return None
    sides = re.split(r"\s+to\s+", _plain(value))
    # "30 to 35 minutes": a side without a unit takes the next side's.
    unit = next((u for u in reversed(re.findall(r"(hours?|hrs?|minutes?|mins?)", value, re.I))), "minutes")
    out = []
    for side in sides:
        pairs = re.findall(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)?", side, re.I)
        minutes = sum(float(n) * (60 if (u or unit).lower().startswith("h") else 1) for n, u in pairs)
        if minutes:
            out.append(minutes)
    return (out[0], out[-1]) if out else None


def temperatures(text: str) -> set[int]:
    return {int(t) for t in TEMPERATURE.findall(text)} | {int(t) for t in OVEN_NUMBER.findall(text)}


def metadata(md: str) -> dict[str, str]:
    """recipe.md's metadata bullets, "Not specified" values included."""
    return {k.strip(): v.strip() for k, v in re.findall(r"^- \*\*([^:*]+):\*\*(.*)$", md, flags=re.M)}


def _minutes(m: float) -> str:
    h, mm = divmod(round(m), 60)
    return (f"{h} hour{'s' * (h != 1)}" + (f" {mm} minutes" if mm else "")) if h else f"{mm} minutes"


def _span(lo: float, hi: float) -> str:
    return _minutes(lo) if lo == hi else f"{_minutes(lo)} to {_minutes(hi)}"


# ---- recipe checks ------------------------------------------------------------------

CONNECTORS = {"and", "or", "the", "a", "an", "to", "of", "with", "in", "until", "then", "for", "into",
              "at", "on", "add", "about", "but", "if", "when", "from", "by", "over", "under"}


def _cut_off(text: str) -> bool:
    """Whether text stops mid-sentence: on a comma, hyphen, or connecting word."""
    text = text.rstrip()
    if not text:
        return False
    last = re.findall(r"[A-Za-z]+", text.splitlines()[-1].lower())
    return text[-1] in ",;:-–(" or bool(last and last[-1] in CONNECTORS and text[-1].isalpha())


# A word a method uses; a source with none of them gives no method at all.
METHOD_VERB = re.compile(r"\b(?:bake|boil|mix|stir|beat|add|put|pour|cook|fry|roast|simmer|steam|cut|chop|"
                         r"serve|melt|cream|fold|spread|roll|cover|heat|place|let|take|turn|set|drain|"
                         r"season|sift|whip|blend|combine|knead|slice|grate|stew|broil|toast|chill)\b", re.I)


def check_truncated(r, add) -> None:
    source = r.original_text.strip()
    if source and _cut_off(source):
        add("error", "truncated", f"the transcription ends mid-sentence: “…{source[-60:].strip()}”")
    inner = source.splitlines()[1:-1]
    if any(re.fullmatch(r"\s*\d{1,3}\s*", line) for line in inner):
        add("warning", "truncated", "a page number sits inside the transcription: check the text on both "
                                    "sides of the page break was joined in order")
    if r.directions and _cut_off(r.directions[-1]):
        add("error", "truncated", f"the last direction ends mid-sentence: “…{r.directions[-1][-60:]}”")
    listed = [i for i in r.ingredients if not i.startswith("## ")]
    if listed and not r.directions:
        if source and not METHOD_VERB.search(source):
            # Old receipt books often give a cake as its ingredients alone.
            add("warning", "no method", "the original gives no method: print it without one, or add the "
                                        "family's way as a note")
        else:
            add("error", "truncated", "the recipe has ingredients but no directions")
    if r.directions and not listed:
        add("error", "truncated", "the recipe has directions but an empty ingredient list")


def check_times(r, meta: dict[str, str], add) -> None:
    # The method's own steps; Notes often give a variation's time, not this one's.
    stated = durations("\n".join(r.directions)) or durations(r.original_text)
    value = meta.get("Cook time", "")
    # "20 minutes per pound" is a rate, not a time to check against the steps.
    cook = None if re.search(r"\bper\s+(?:pound|lb|inch|kilo)", value, re.I) else meta_minutes(value)
    cooking = [(a, b) for a, b, k in stated if k == "cook"]
    if cook is None:
        if cooking and value.lower().startswith("not"):
            lo, hi = sum(a for a, _ in cooking), sum(b for _, b in cooking)
            add("note", "cook time", f"the directions give {_span(lo, hi)} of cooking; Cook time says Not specified")
    elif stated:
        # The times the text supports: every cooking stage summed ("sum every
        # timed stage"), with or without short rests (a steep, a stand; a long
        # chill or marinade never counts); the sum less one stage, a step that
        # runs alongside another (the pasta boiling while the sauce simmers); or
        # the longest stage alone when it is most of the cooking. Ranges carry
        # through ("bake six or eight hours" holds 8 hours). Any other single
        # stage is the "first number in the text" error. An "About" time may
        # round, by a tenth.
        base = cooking or [(a, b) for a, b, k in stated if k != "within"] or [(a, b) for a, b, _ in stated]
        rests = [(a, b) for a, b, k in stated if k == "rest" and b <= 30] if cooking else []
        lo, hi = sum(a for a, _ in base), sum(b for _, b in base)
        candidates = [(lo, hi), (lo + sum(a for a, _ in rests), hi + sum(b for _, b in rests))]
        longest = max(base, key=lambda s: s[1])
        # A stage that runs alongside another is the shorter of the two: drop
        # any stage but the longest, never leave a short stage standing alone.
        candidates += [(lo - a, hi - b) for i, (a, b) in enumerate(base) if i != base.index(longest)]
        if longest[1] >= MOST_OF_THE_COOKING * hi:
            candidates.append(longest)
        slack = (lambda m: max(1, m * 0.1)) if value.lower().startswith("about") else (lambda m: 1)
        if not any(a - slack(a) <= cook[0] and cook[1] <= b + slack(b) for a, b in candidates):
            listed = ", ".join(_span(a, b) for a, b, _ in stated)
            add("warning", "cook time", f"Cook time is {_span(*cook)}, but the directions state {listed}")
    else:
        add("warning", "cook time", f"Cook time is {_span(*cook)}, but no time appears in the directions or the source")

    stated_temps = temperatures("\n".join(r.directions + r.notes)) | temperatures(r.original_text)
    temp = meta.get("Temperature", "")
    figure = re.search(r"\d{3}", temp)
    if figure and stated_temps and int(figure.group()) not in stated_temps:
        add("warning", "cook time", f"Temperature is {temp}, but the recipe states "
                                    f"{', '.join(f'{t}°' for t in sorted(stated_temps))}")
    elif not figure and temp.lower().startswith("not") and stated_temps:
        add("warning", "cook time", f"the directions bake at {', '.join(f'{t}°' for t in sorted(stated_temps))}; "
                                    "Temperature says Not specified")


# The share of all timed cooking the longest stage must hold to stand alone as
# the Cook time.
MOST_OF_THE_COOKING = 0.6
YIELD_WORDS = re.compile(r"\b(?:serves?|servings?|persons?|people|yields?|makes?|enough for|portions?|pieces?|"
                         r"dozen|loaf|loaves|cakes?|cookies|muffins|biscuits|pies?|quarts?|pints?|cups?|glasses)\b",
                         re.I)


def check_invented(r, meta: dict[str, str], add, estimates: bool = False) -> None:
    """Figures with no source behind them: a metadata value a cook would have
    had to guess, or an ingredient amount that differs from the original. With
    `estimates` (book.yaml `audit: estimates: true`), a Yield or Prep time
    written "About …" is the family's estimate and passes."""
    from .ingest import _amounts, _stated

    if not r.original_text.strip():
        return
    source = _stated(r.original_text)
    # A Yield's figure must come from text about servings, not from any number
    # in the recipe ("bake six or eight hours" does not serve eight): the words
    # around each yield word, since an abbreviation ("3/4 lb.") breaks a sentence.
    flat = " ".join(r.original_text.split())
    yield_source = _stated(" ".join(flat[max(0, m.start() - 60): m.end() + 30] for m in YIELD_WORDS.finditer(flat)))
    for key in ("Yield", "Prep time", "Temperature"):
        value = meta.get(key, "")
        if estimates and key != "Temperature" and value.lower().startswith("about"):
            continue
        stated = yield_source if key == "Yield" else source
        if [n for n in _amounts(value) if n not in stated]:
            add("warning", "invented", f"{key} “{value}” is not in the source")
    for item in (i for i in r.ingredients if not i.startswith("## ")):
        missing = [n for n in _amounts(item) if n not in source]
        if missing:
            add("warning", "invented", f"the ingredient “{item}” gives {', '.join(missing)}, which the source does not")


# Foods a method names. A head noun matches its plurals and any ingredient line
# containing it ("sugar" matches "brown sugar"); two-word entries match as
# phrases. Verbs that are also foods ("cream the butter") are left out.
FOODS = set("""
almond apple apricot asparagus avocado bacon baking-powder banana basil bay bean beef beer bell biscuit bisquick
blueberry bourbon brandy bread breadcrumb broccoli broth brown-sugar buttermilk cabbage carrot cashew
cauliflower celery cheddar cheese cherry chicken chili chive chocolate cilantro cinnamon clam clove
cocoa coconut coffee cognac corn cornmeal cornstarch crab cracker cranberry cream-cheese cucumber cumin
date dill egg eggplant evaporated-milk fish fish-sauce garlic gelatin ginger graham ham honey horseradish
jalapeno jam jello jelly ketchup lamb lard leek lemon lettuce lime macaroni maple-syrup corn-syrup
margarine marshmallow mayonnaise milk mint molasses mozzarella mushroom mustard noodle nut nutmeg oat
olive olive-oil onion orange oregano paprika parmesan parsley pasta pea peach peanut pear pecan pepperoni
pickle pineapple pistachio pork potato powdered-sugar pretzel pudding pumpkin raisin raspberry rice
ricotta rum sage salami salmon sausage scallion sherry shrimp soda sour-cream soy spinach squash
steak strawberry sugar tartar teriyaki tomato tortilla tuna turkey vanilla vinegar walnut whipped-cream
whiskey wine worcestershire yeast yogurt zucchini pie-shell soup-mix
""".split())
# A general word in a method is named by any of its kinds in the list:
# "cheese" by cheddar, "crackers" by saltines, "noodles" by macaroni.
KINDS = {
    "cheese": "cheddar mozzarella parmesan swiss american velveeta ricotta monterey jack colby provolone feta "
              "gruyere cheez brie gouda muenster",
    "cracker": "saltine ritz graham club oyster triscuit",
    "noodle": "macaroni pasta spaghetti penne elbow fettuccine linguine ziti rotini shell lasagna egg-noodle",
    "pasta": "macaroni noodle spaghetti penne elbow fettuccine linguine ziti rotini shell lasagna",
    "breadcrumb": "bread crumb panko stuffing",
    "nut": "walnut pecan almond peanut cashew hazelnut pistachio",
    "fish": "cod haddock salmon tuna tilapia flounder halibut sole trout",
    "wine": "claret sherry burgundy chardonnay merlot port",
}
# Greasing the pan, seasoning to taste: often left out of a list on purpose.
PAN_PREP = set("butter flour oil shortening water salt pepper ice spray".split())
# A food word naming a tool, not a food: "potato ricer", "egg beater".
TOOLS = set("ricer masher beater peeler pan dish bowl pot board cutter press slicer grater mold mould tin "
            "cup cups spoon knife squeezer".split())
SERVING = re.compile(r"\bserve|\bgarnish|\bsprinkle with|\btop with|\baccompan", re.I)
# A food word followed by one of these in the list names something made from
# it: "almond extract" does not list almonds, "garlic powder" does not list garlic.
DERIVED = set("extract flavoring juice oil paste powder zest milk butter sauce syrup liqueur seasoning "
              "flake essence soup mix".split())


# Words that end in s and are not plurals.
INVARIANT = set("molasses asparagus hummus couscous citrus swiss bass grass glass cress tapioca".split())


def _singular(word: str) -> str:
    if word in INVARIANT or word.endswith("ss"):
        return word
    for suffix, repl in (("ies", "y"), ("oes", "o"), ("es", "e"), ("s", "")):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            return word[: -len(suffix)] + repl
    return word


def _words(text: str) -> list[str]:
    text = re.sub(r"\bjell[-\s]?o\b", "jello", text.lower().replace("’", "'"))
    # "Sweeten to taste" uses sugar as surely as "add sugar" does.
    text = re.sub(r"\bsweeten(?:ed)?\b", "sugar", text)
    return [_singular(w) for w in re.findall(r"[a-z][a-z'-]*", text)]


def _stem(word: str) -> str:
    """A word without -ed, -ing, or a final e, for comparing a sentence with its
    rewording: "cubed", "cubes", and "cube" all read "cub"; "skimmed" and
    "skimming" read "skim"."""
    for suffix in ("ing", "ed"):
        if word.endswith(suffix) and len(word) > len(suffix) + 2:
            word = word[: -len(suffix)]
            if len(word) > 3 and word[-1] == word[-2] and word[-1] not in "aeiouls":
                word = word[:-1]  # "skimm" -> "skim", but "spell" and "dress" keep theirs
            break
    return word[:-1] if word.endswith("e") and len(word) > 3 else word


def check_ingredients(r, add) -> None:
    listed = " ".join(_words(" ".join(r.ingredients)))
    tokens = listed.split()
    listed_words = {w for w, nxt in zip(tokens, tokens[1:] + [""]) if not (w in FOODS and nxt in DERIVED)}
    # The dish itself, by its title's last word: "the bread in rising" in Boston
    # Brown Bread. Other title words are ingredients (the almonds in Almond Roca).
    named = set(_words(r.title)[-1:])
    seen: set[str] = set()
    for step in r.directions:
        words = _words(step)
        after = dict(zip(words, words[1:]))
        pairs = [f"{a}-{b}" for a, b in zip(words, words[1:])]
        for food in pairs + words:
            name = food.replace("-", " ")
            if food in seen or (food not in FOODS and food not in PAN_PREP):
                continue
            parts = food.split("-")
            # A phrase is named by its head ("olive oil" by "oil"); a word inside
            # a listed phrase of this step is judged with that phrase; "almond
            # extract" in the method is named by "almond extract" in the list.
            if (all(p in listed_words for p in parts) or ("-" in food and name in listed) or set(parts) <= named
                    or ("-" in food and parts[-1] in listed_words)
                    or (after.get(food) in DERIVED and f"{food} {after[food]}" in listed)):
                continue
            if after.get(parts[-1]) in TOOLS or after.get(parts[-1]) in {"out", "them", "it"}:
                continue
            if "-" not in food and any(p.startswith(f"{food}-") for p in pairs if p in FOODS):
                continue
            if food in KINDS and listed_words & set(_words(KINDS[food])):
                continue
            seen.add(food)
            garnish = bool(SERVING.search(step))
            severity = "note" if food in PAN_PREP or garnish else "warning"
            use = "serves it with" if garnish else "uses"
            add(severity, "ingredients", f"the method {use} {name}, which the ingredient list does not name")


STOPWORDS = set("""
the and for with that this from into until then when your you are was were have has had will can not but
all any each its it's let them they their there these those about over under more less very just some
also add put use set get one two three four five six seven eight nine ten cup cups teaspoon teaspoons
tablespoon tablespoons pound pounds ounce ounces minute minutes hour hours degree degrees inch inches
""".split())
# A source line of label-colon-value pairs ("Servings: 4  Time: 45 Minutes"):
# metadata, which the invented and cook time checks read.
META_LINE = re.compile(r"\b(?:servings?|serves|yields?|makes|prep(?:aration)?(?: time)?|cook(?:ing)? time|"
                       r"bake time|temp\w*|time|oven)\s*:", re.I)


def check_dropped(r, add) -> None:
    """Sentences of the source the recipe does not carry, by their words."""
    source = r.original_text.strip()
    if not source:
        return
    meta = " ".join(metadata((r.folder / "recipe.md").read_text(encoding="utf-8")).values()) \
        if (r.folder / "recipe.md").exists() else ""
    printed = {_stem(w) for w in _words(" ".join([r.title, meta, *r.ingredients, *r.directions, *r.notes, *r.prose]))}
    lines = [line.strip() for line in source.splitlines()]
    if lines and set(_words(lines[0])) <= set(_words(r.title)) | {"recipe"}:
        lines = lines[1:]  # the transcription's own title line
    text = " ".join(lines)
    for sentence in re.split(r"(?<=[.!?])[)\"”’]*\s+", text):
        if META_LINE.search(sentence):
            continue
        words = [_stem(w) for w in _words(sentence) if len(w) > 2 and w not in STOPWORDS and not w.isdigit()]
        if len(words) < 4:
            continue
        kept = sum(w in printed for w in words) / len(words)
        if kept < 0.5:
            add("warning", "dropped", f"this line of the source is not in the recipe: “{sentence.strip()[:140]}”")


# Marks a transcription leaves for a person: an unread word, an unsure reading,
# or stray symbols where a line was garbled ("3 teaspoons baking powder > 2 cups").
UNCLEAR = re.compile(r"\[(?:illegible|\?)\]|\w\s*\[\?\]|(?<![<>=])[<>|](?![<>=])")
REFERENCE = re.compile(r"\b(?:the )?above(?: ingredients)?\b|\bingredients (?:listed )?above\b", re.I)


def check_unclear(r, add) -> None:
    for item in [*r.ingredients, *r.directions]:
        if UNCLEAR.search(item):
            add("warning", "unclear", f"“{item[:120]}” keeps a mark or symbol the transcription left: check it "
                                      "against the original")
    for n, step in enumerate(r.directions, 1):
        if REFERENCE.search(step) and not any(i.startswith("## ") for i in r.ingredients):
            add("note", "reference", f"step {n} refers to “{REFERENCE.search(step).group().strip()}”: check the "
                                     "list still shows which ingredients")


# Source abbreviations, spelled out before comparing words.
ABBREVIATIONS = {"tsp": "teaspoon", "tbsp": "tablespoon", "tbs": "tablespoon", "tbl": "tablespoon",
                 "lb": "pound", "oz": "ounce", "pkg": "package", "qt": "quart", "pt": "pint",
                 "doz": "dozen", "sm": "small", "lg": "large", "med": "medium", "approx": "about"}
# Words a clean ingredient line may add without changing it.
FORM_WORDS = STOPWORDS | set("""
package packages can cans stick sticks quart quarts pint pints dozen large small medium optional divided
taste each plus more needed whole fresh cut piece pieces slice slices about
""".split())


# An action that happens in the pot, not on the cutting board: in an ingredient
# line ("1 quart milk, brought to a boil and poured over the chocolate"), it is a
# step of the method a cook reading the list will miss. Preparation ("cut in
# slices", "well beaten") belongs to an ingredient.
STEP_IN_LIST = re.compile(r"\b(?:brought to a boil|bring to a boil|poured over|pour over|boiled until|cooked until|"
                          r"stirred into|added to|baked for|simmered|heated until|then (?:add|stir|pour|bake|boil))\b",
                          re.I)


def check_changed(r, add) -> None:
    """Ingredient lines that say something the source does not: "ground
    cinnamon" where the card says "browned cinnamon"."""
    source = r.original_text.strip()
    if not source:
        return
    said = {_stem(ABBREVIATIONS.get(w, w)) for w in _words(source + " " + r.title)}
    for item in (i for i in r.ingredients if not i.startswith("## ")):
        if STEP_IN_LIST.search(item):
            add("warning", "changed", f"“{item[:100]}” holds a step of the method: move it to Directions")
            continue
        new = [w for w in _words(item) if len(w) > 3 and w not in FORM_WORDS
               and _stem(ABBREVIATIONS.get(w, w)) not in said]
        if new:
            add("warning", "changed", f"“{item}” says {', '.join(dict.fromkeys(new))}, which the source does not")


# ---- book checks ----------------------------------------------------------------------

NICKNAMES = [
    {"robert", "bob", "bobby", "rob"}, {"william", "bill", "billy", "will"}, {"margaret", "peggy", "maggie", "meg"},
    {"elizabeth", "liz", "beth", "betty", "betsy", "eliza"}, {"katherine", "catherine", "kathy", "cathy", "kate", "katie"},
    {"richard", "dick", "rick", "rich"}, {"james", "jim", "jimmy"}, {"john", "jack", "johnny"},
    {"patricia", "pat", "patty", "trish"}, {"susan", "sue", "susie"}, {"deborah", "debbie", "deb"},
    {"thomas", "tom", "tommy"}, {"joseph", "joe", "joey"}, {"michael", "mike", "mikey"},
    {"barbara", "barb", "barbie"}, {"jennifer", "jen", "jenny"}, {"dorothy", "dot", "dottie"},
    {"edward", "ed", "eddie", "ted"}, {"charles", "charlie", "chuck"}, {"mary", "molly", "polly"},
    {"helen", "nell", "nellie"}, {"virginia", "ginny", "ginger"}, {"frances", "fran", "frannie"},
]


def _edit_distance(a: str, b: str) -> int:
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def same_person(a: str, b: str) -> str:
    """Why two credits probably name one person, or "" when they do not."""
    na, nb = (re.sub(r"[^a-z ]", "", n.lower()).split() for n in (a, b))
    if not na or not nb or na == nb:
        return "" if na == nb and a == b else ("spelled differently" if na == nb else "")
    first_a, first_b = na[0], nb[0]
    last_a, last_b = (na[-1] if len(na) > 1 else ""), (nb[-1] if len(nb) > 1 else "")
    if last_a and last_b and last_a != last_b:
        if first_a == first_b and _edit_distance(last_a, last_b) <= 1 and min(len(last_a), len(last_b)) >= 4:
            return "surnames one letter apart"
        return ""
    if first_a == first_b:
        return "one credit has a surname, the other does not" if last_a != last_b else ""
    if any(first_a in group and first_b in group for group in NICKNAMES):
        return "a nickname and a given name"
    if min(len(first_a), len(first_b)) >= 3 and (first_a.startswith(first_b) or first_b.startswith(first_a)):
        return "a short form of the same name"
    if min(len(first_a), len(first_b)) >= 4 and _edit_distance(first_a, first_b) <= 1:
        return "first names one letter apart"
    return ""


EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?<![\d/])(?:\(\d{3}\)\s*|\d{3}[-.\s])\d{3}[-.]\d{4}(?!\d)")
ADDRESS = re.compile(r"\b\d{2,5}\s+(?:[A-Z][a-z]+\s+){1,3}(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|"
                     r"Boulevard|Blvd|Court|Ct|Way|Place|Pl|Circle|Cir|Terrace|Highway|Hwy)\b\.?")


def personal_data(text: str) -> list[str]:
    found = [f"an email address ({m})" for m in EMAIL.findall(text)]
    found += [f"a phone number ({m})" for m in PHONE.findall(text)]
    found += [f"a street address ({m})" for m in ADDRESS.findall(text)]
    return found


# ---- running it ---------------------------------------------------------------------------

@dataclass
class Entry:
    key: str
    title: str
    page: int | None
    folder: Path


def entry_findings(r, md: str, estimates: bool = False) -> list[Finding]:
    """The per-recipe content checks on one parsed recipe and its recipe.md."""
    key = r.folder.relative_to(r.folder.parents[2]).as_posix()
    found: list[Finding] = []

    def add(severity: str, check: str, message: str) -> None:
        found.append(Finding(severity, check, key, message))

    meta = metadata(md)
    if r.ingredients or r.directions:
        check_truncated(r, add)
        check_times(r, meta, add)
        check_invented(r, meta, add, estimates)
        check_ingredients(r, add)
        check_changed(r, add)
        check_unclear(r, add)
    check_dropped(r, add)
    for item in personal_data(md):
        add("error", "personal data", f"prints {item}")
    return found


def collect(root: config.BookRoot, run_check: bool = False) -> tuple[list[Finding], dict[str, Entry]]:
    from . import fit_images, lint, render

    recipes = render.assemble_recipes()
    estimates = config.load(root).estimates
    _, shown = render.build(recipes)
    first_page: dict[Path, int] = {}
    for p in shown:
        if p.page_number and not p.is_generated and p.folder not in first_page:
            first_page[p.folder] = p.page_number

    findings: list[Finding] = []
    entries: dict[str, Entry] = {}
    credits: dict[str, list[str]] = defaultdict(list)
    for r in recipes:
        if r.is_generated or r.is_divider or r.is_chapter_page:
            continue
        md_name = "recipe.md" if (r.folder / "recipe.md").exists() else "page.md"
        md_path = r.folder / md_name
        if not md_path.exists():
            continue
        key = md_path.parent.relative_to(root.book).as_posix()
        entries[key] = Entry(key, r.title, first_page.get(r.folder), r.folder)
        md = md_path.read_text(encoding="utf-8")
        findings += [Finding(f.severity, f.check, key, f.message) for f in entry_findings(r, md, estimates)]
        extras = r.folder / "extras" / "extras.md"
        if extras.exists():
            for item in personal_data(extras.read_text(encoding="utf-8")):
                findings.append(Finding("error", "personal data", key, f"a keepsake caption prints {item}"))
        for name in render.credited_cooks(r.attribution):
            credits[name].append(key)

    for a, b in combinations(sorted(credits), 2):
        why = same_person(a, b)
        if why:
            where = "; ".join(f"“{n}” on {', '.join(entries[k].title for k in credits[n])}" for n in (a, b))
            findings.append(Finding("warning", "same cook", "",
                                    f"“{a}” and “{b}” probably name one person ({why}): {where}"))
    if root.cover_copy_path.exists():
        for item in personal_data(root.cover_copy_path.read_text(encoding="utf-8")):
            findings.append(Finding("error", "personal data", "", f"the back cover prints {item}"))

    rep = lint.collect()
    by_path = sorted(entries, key=len, reverse=True)

    def owner(line: str) -> str:
        return next((k for k in by_path if f"book/{k}/" in line or line.startswith(f"book/{k}:")), "")

    findings += [Finding("error", "lint", owner(l), l) for l in rep.errors]
    findings += [Finding("warning", "lint", owner(l), l) for l in rep.warnings]

    for r in recipes:
        if r.has_image and r.archetype in render.PHOTO_FRAMES:
            key = r.folder.relative_to(root.book).as_posix()
            fit = render.photo_fit(r, r.archetype)
            if fit.problem:
                findings.append(Finding("warning", "photo", key, f"{r.archetype}: {fit.problem}"))
            need = render.photo_frame(r, r.archetype)[1] * render.PRINT_PPI
            if fit.box[2] - fit.box[0] < need * fit_images.LOW_RES_SHARE:
                findings.append(Finding("warning", "photo", key, f"{r.archetype}: {fit.box[2] - fit.box[0]}px wide, "
                                                                 f"under {round(need)}px for crisp print"))

    if run_check:
        from . import check

        html_path = root.draft / "cookbook-print.html"
        for page in check.failing_pages(html_path):
            where = f"page {page['num']}" if page["num"] else f"PDF page {page['idx']}"
            findings.append(Finding("error", "overflow", page["key"],
                                    f"{where}: {page['problem']} {page['fix']}"))
    return findings, entries


def write_report(root: config.BookRoot, findings: list[Finding], entries: dict[str, Entry]) -> Path:
    cfg = config.load(root)
    out = root.draft / "book-report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    counts = {s: sum(f.severity == s for f in findings) for s in SEVERITIES}
    body = []
    for severity in SEVERITIES:
        group = [f for f in findings if f.severity == severity]
        if not group:
            continue
        body.append(f'<section><h2 class="{severity}">{severity.title()}s <span>{len(group)}</span></h2>')
        by_entry: dict[str, list[Finding]] = defaultdict(list)
        for f in group:
            by_entry[f.entry].append(f)
        order = sorted(by_entry, key=lambda k: (k != "", entries[k].page or 10**6 if k in entries else 0, k))
        for key in order:
            e = entries.get(key)
            if e:
                page = f'<a href="cookbook-draft.html#p{e.page}">page {e.page}</a> · ' if e.page else ""
                head = (f'<h3>{html.escape(e.title)}</h3><p class="where">{page}'
                        f'<a href="../book/{html.escape(key)}/">book/{html.escape(key)}</a></p>')
            else:
                head = "<h3>The whole book</h3>" if key == "" else f"<h3>{html.escape(key)}</h3>"
            items = "".join(f"<li><b>{html.escape(f.check)}</b> {html.escape(f.message)}</li>" for f in by_entry[key])
            body.append(f"<article>{head}<ul>{items}</ul></article>")
        body.append("</section>")

    summary = " · ".join(f"{counts[s]} {s}{'s' * (counts[s] != 1)}" for s in SEVERITIES)
    if findings:
        summary += f". By check: {html.escape(by_check(findings))}"
    if cfg.estimates:
        summary += ". Yields and Prep times written “About …” are accepted as the family’s estimates (book.yaml audit.estimates)"
    out.write_text(REPORT.format(title=html.escape(cfg.title), summary=summary,
                                 body="\n".join(body) or "<p>Nothing flagged.</p>"), encoding="utf-8")
    return out


def by_check(findings: list[Finding]) -> str:
    """The findings counted by check, most first ("invented 120 · cook time 3"): where review time goes."""
    counts: dict[str, int] = defaultdict(int)
    for f in findings:
        counts[f.check] += 1
    return " · ".join(f"{check} {n}" for check, n in sorted(counts.items(), key=lambda kv: -kv[1]))


def main(root: config.BookRoot, run_check: bool = False) -> int:
    findings, entries = collect(root, run_check)
    out = write_report(root, findings, entries)
    for severity in ("error", "warning"):
        for f in (f for f in findings if f.severity == severity):
            where = entries[f.entry].title if f.entry in entries else (f.entry or "book")
            print(f"{severity.upper():8} {f.check:14} {where}: {f.message}")
    counts = {s: sum(f.severity == s for f in findings) for s in SEVERITIES}
    print(f"\n{counts['error']} error(s), {counts['warning']} warning(s), {counts['note']} note(s) "
          f"across {len(entries)} entries — {out.relative_to(root.path)}")
    if findings:
        print(f"By check: {by_check(findings)}")
    if not run_check:
        print("Overflow and type size are not in this report: add --check after cookbook build --print.")
    return 1 if counts["error"] else 0


REPORT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Book report — {title}</title>
<style>
  body {{ font: 15px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; color: #2a2622; background: #faf7f2;
         max-width: 60rem; margin: 0 auto; padding: 2rem 1.25rem 4rem; }}
  h1 {{ margin: 0; font-size: 1.6rem; }}
  .summary {{ color: #6b635b; margin: .25rem 0 2rem; }}
  h2 {{ font-size: 1.1rem; margin: 2rem 0 .75rem; padding-bottom: .3rem; border-bottom: 2px solid currentColor; }}
  h2 span {{ font-weight: 400; color: #6b635b; }}
  h2.error {{ color: #a3271f; }} h2.warning {{ color: #9a4a12; }} h2.note {{ color: #4d5b66; }}
  article {{ margin: 0 0 1.1rem; }}
  h3 {{ font-size: 1rem; margin: 0; }}
  .where {{ margin: 0 0 .3rem; font-size: .85rem; color: #6b635b; }}
  a {{ color: #8a5a2b; }}
  ul {{ margin: 0; padding-left: 1.1rem; }}
  li {{ margin: .15rem 0; }}
  li b {{ font-size: .72rem; letter-spacing: .06em; text-transform: uppercase; color: #6b635b; margin-right: .3rem; }}
</style></head>
<body>
<h1>Book report: {title}</h1>
<p class="summary">{summary}. Generated by <code>cookbook audit</code>; page links open the screen draft.</p>
{body}
</body></html>
"""
