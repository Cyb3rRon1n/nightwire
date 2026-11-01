import pytest

from narrator.design_sheets import expression_prompts, sheet_prompt
from narrator.designs import validate
from ruleset.lifepaths import LIFEPATHS
from ruleset.roles import ROLES
from tools import character_answers as ca


def good(**k):
    return {"name": "Vex", "presentation": "feminine", **k}


def question(qid):
    return next(q for q in ca.QUESTIONS if q["id"] == qid)


def test_required_and_choices_are_enforced():
    with pytest.raises(ca.BadAnswers, match="name"):
        ca.clean_answers({"presentation": "feminine"})
    with pytest.raises(ca.BadAnswers, match="presentation"):
        ca.clean_answers({"name": "Vex", "presentation": "robot"})


def test_weight_syntax_and_refused_words():
    assert ca.clean_answers(good(hair="(silver hair:1.6), <lora:x:1>"))["hair"] == "silver hair"
    with pytest.raises(ca.BadAnswers, match="nude"):
        ca.clean_answers(good(outfit="nude"))


def test_unknown_fields_are_dropped_and_length_capped():
    got = ca.clean_answers(good(hacker="x", hair="a" * 999))
    assert "hacker" not in got and len(got["hair"]) == 120


def test_design_fields_go_where_the_sheets_expect():
    d = ca.to_design(ca.clean_answers(good(hair="silver hair", eyes="red eyes", marks="scar on left cheek",
                                           chrome="mechanical right arm", signature="katana", never="glasses",
                                           outfit="trench coat", lifepath="corpo", backstory="ignored words")),
                     "player", 42)
    assert d.required == ["silver hair", "red eyes", "scar on left cheek", "mechanical right arm"]
    assert d.held == ["katana"] and "glasses" in d.negative and d.seed == 42 and d.presentation == "feminine"
    assert "trench coat" in d.tags and "corporate" in d.tags and "ignored" not in d.tags
    assert "adult" in d.tags


def test_blank_marks_and_chrome_add_nothing():
    d = ca.to_design(ca.clean_answers(good()), "player", 1)
    assert d.required == [] and "tattoo" not in d.tags and "mechanical" not in d.tags


def test_questions_cover_every_step_and_the_games_own_lists():
    assert [q["id"] for q in ca.QUESTIONS if q["required"]] == ["name", "presentation"]
    assert {q["step"] for q in ca.QUESTIONS} == {"basics", "look", "nightwire", "final"}
    assert question("role")["choices"] == list(ROLES) and question("lifepath")["choices"] == list(LIFEPATHS)
    assert {"world_role", "home"} == {q["id"] for q in ca.QUESTIONS if q.get("world_only")}
    assert all(lifepath in ca._LIFEPATH_TAGS for lifepath in LIFEPATHS)


@pytest.mark.parametrize("sneaky, words", [("((nude:1.4))", "nude"), ("n<x>ude", "nude"), ("nude_body", "nude"),
                                           ("(nude:1.4", "nude"), ("NAKED", "naked"), ("schoolgirl uniform", "schoolgirl")])
def test_refusals_see_through_the_cleaning_and_name_the_field(sneaky, words):
    with pytest.raises(ca.BadAnswers, match=words) as e:
        ca.clean_answers(good(outfit=sneaky))
    assert "outfit" in str(e.value).lower()


@pytest.mark.parametrize("field", ["name", "personality", "backstory", "extra", "world_role", "home", "never"])
def test_words_that_never_reach_the_prompt_are_still_screened(field):
    with pytest.raises(ca.BadAnswers, match="nude"):
        ca.clean_answers(good(**{field: "nude"}))


@pytest.mark.parametrize("text", ["16yo", "looks 14 years old", "a young woman", "petite and youthful"])
def test_free_text_cant_ask_for_someone_underage(text):
    # refused_terms drops digits and doesn't know "young" alone, so this list sits on top of it.
    with pytest.raises(ca.BadAnswers):
        ca.clean_answers(good(extra=text))


@pytest.mark.parametrize("text", ["adult", "mature face, old", "clothes", "any clothing"])
def test_never_cant_cancel_the_adult_or_clothed_rule(text):
    # A negative prompt of "adult" or "clothes" asks for exactly what art direction forbids.
    with pytest.raises(ca.BadAnswers, match="must never"):
        ca.clean_answers(good(never=text))
    assert ca.clean_answers(good(outfit="mature style, old coat, clothes"))["outfit"]


@pytest.mark.parametrize("raw", [["not", "an", "object"], "text", None])
def test_answers_must_be_an_object(raw):
    with pytest.raises(ca.BadAnswers):
        ca.clean_answers(raw)


@pytest.mark.parametrize("field", ["name", "hair", "presentation"])
def test_non_text_values_are_refused(field):
    with pytest.raises(ca.BadAnswers):
        ca.clean_answers(good(**{field: ["x"]}))


def test_blank_optional_answers_are_dropped():
    assert ca.clean_answers(good(hair="   ", age="", role=None)) == good()


@pytest.mark.parametrize("age, tag", [("20s", "young adult"), ("30s", "mature"), ("40s", "middle-aged"), ("50+", "old")])
def test_age_tags_stay_adult(age, tag):
    tags = [t.strip() for t in ca.to_design(ca.clean_answers(good(age=age)), "player", 1).tags.split(",")]
    assert tag in tags and "young" not in tags
    assert len(tags) == len(set(tags)) and tags[:2] == ["mature", "adult"]


@pytest.mark.parametrize("lifepath, tag", [("corpo", "corporate attire"), ("streetkid", "street fashion"),
                                           ("nomad", "nomad gear"), ("tsukumogami", "android")])
def test_lifepath_adds_a_style_tag(lifepath, tag):
    assert tag in ca.to_design(ca.clean_answers(good(lifepath=lifepath)), "player", 1).tags


def test_role_personality_and_world_fields_stay_out_of_the_prompt():
    d = ca.to_design(ca.clean_answers(good(role="solo", personality="grumpy", world_role="ramen cook",
                                           home="Dock Nine", backstory="left the docks")), "npc", 1)
    prompt = " ".join(sheet_prompt(d, "turnaround"))
    for word in ("solo", "grumpy", "ramen", "Dock", "docks"):
        assert word not in d.tags and word not in prompt.replace("solo,", "")
    assert any("grumpy" in n for n in d.notes)


def test_every_answer_meant_for_the_picture_reaches_the_prompt():
    d = ca.to_design(ca.clean_answers(good(skin="dark skin", build="tall", face_extras="red lipstick", outfit="leather jacket",
                                           colours="black and teal", extra="glowing visor")), "player", 1)
    positive = sheet_prompt(d, "turnaround")[0]
    for word in ("dark skin", "tall", "red lipstick", "leather jacket", "black and teal", "glowing visor"):
        assert word in positive


def test_facial_features_are_required_so_they_survive_close_ups():
    d = ca.to_design(ca.clean_answers(good(face_extras="short beard, red lipstick")), "player", 1)
    assert d.required == ["short beard", "red lipstick"]
    assert all("short beard" in pos for _, pos, _ in expression_prompts(d))


def test_signature_item_shows_on_body_views_but_not_in_close_ups():
    d = ca.to_design(ca.clean_answers(good(signature="katana")), "player", 1)
    assert "katana" in sheet_prompt(d, "turnaround")[0]
    assert all("katana" not in pos and "katana" in neg for _, pos, neg in expression_prompts(d))


@pytest.mark.parametrize("kind", ["player", "npc", "ai"])
def test_the_design_is_a_valid_character_with_a_source_naming_the_kind(kind):
    d = ca.to_design(ca.clean_answers(good()), kind, 7)
    validate(d)
    assert d.kind == "character" and d.source == f"creator:{kind}" and d.name == "Vex"


def test_adult_negatives_are_applied():
    negative = sheet_prompt(ca.to_design(ca.clean_answers(good()), "player", 1), "turnaround")[1]
    assert "loli" in negative and "nude" in negative and "young" in negative
