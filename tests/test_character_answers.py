import pytest

from narrator.design_sheets import expression_prompts, sheet_prompt
from narrator.designs import validate
from ruleset.lifepaths import LIFEPATHS
from ruleset.roles import ROLES
from tools import character_answers as ca
from tools import image_studio as st


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
                                           chrome="mechanical right arm", signature="katana", never=["glasses"],
                                           outfit="trench coat", lifepath="corpo", backstory="ignored words")),
                     "player", 42)
    assert d.required == ["silver hair", "red eyes", "scar on left cheek", "mechanical right arm"]
    assert d.held == [] and "katana" in d.tags and "glasses" in d.negative and d.seed == 42 and d.presentation == "feminine"
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


@pytest.mark.parametrize("field", ["name", "personality", "backstory", "extra", "world_role", "home"])
def test_words_that_never_reach_the_prompt_are_still_screened(field):
    with pytest.raises(ca.BadAnswers, match="nude"):
        ca.clean_answers(good(**{field: "nude"}))


@pytest.mark.parametrize("text", ["16yo", "looks 14 years old", "a young woman", "petite and youthful"])
def test_free_text_cant_ask_for_someone_underage(text):
    # refused_terms drops digits and doesn't know "young" alone, so this list sits on top of it.
    with pytest.raises(ca.BadAnswers):
        ca.clean_answers(good(extra=text))


NEVER_CHOICES = ["glasses", "facial hair", "tattoos", "scars", "piercings", "chrome", "makeup", "jewellery", "hats", "hoods", "masks"]


def test_never_is_a_multi_choice_of_harmless_things():
    q = question("never")
    assert q["kind"] == "multi" and q["choices"] == NEVER_CHOICES
    got = ca.clean_answers(good(never=["masks", "glasses", "masks"]))["never"]
    assert got == ["glasses", "masks"]
    assert "never" not in ca.clean_answers(good(never=[]))


# A negative prompt of any of these asks for what art direction forbids, and no blocklist can list every garment.
@pytest.mark.parametrize("word", ["shirt", "pants", "jacket", "underwear", "bra", "skirt", "dress", "coat", "techwear", "attire",
                                  "garments", "fully covered", "woman", "grown-up", "wrinkles", "elderly", "mature_female",
                                  "adult_woman", "clothed_female", "\uff41\uff44\uff55\uff4c\uff54", "adult", "clothes"])
def test_never_refuses_anything_off_the_list(word):
    for value in (word, [word], ["glasses", word]):
        with pytest.raises(ca.BadAnswers, match="must never"):
            ca.clean_answers(good(never=value))


@pytest.mark.parametrize("value", ["glasses", {"a": 1}, 5, [["glasses"]], [None]])
def test_never_must_be_a_list_of_choices(value):
    with pytest.raises(ca.BadAnswers, match="must never"):
        ca.clean_answers(good(never=value))


def test_only_the_choice_list_reaches_a_designs_negative_or_held():
    answers = ca.clean_answers(good(never=["hats"], signature="clothes, adult, mature", outfit="trench coat"))
    d = ca.to_design(answers, "player", 1)
    assert d.held == []
    assert "hats" in d.negative and "clothes" not in d.negative and "adult" not in d.negative and "mature" not in d.negative
    # Even a record that somehow holds free text can't get it into the negative.
    assert "clothes" not in ca.to_design({**answers, "never": "clothes"}, "player", 1).negative
    assert "clothes" not in ca.to_design({**answers, "never": ["clothes"]}, "player", 1).negative
    assert "clothes" not in expression_prompts(d)[0][2].replace("different clothes", "")


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


@pytest.mark.parametrize("age", ["20s", "30s", "40s", "50+"])
def test_age_tags_stay_adult_and_dont_fight_the_negatives(age):
    d = ca.to_design(ca.clean_answers(good(age=age)), "player", 1)
    tags = [t.strip() for t in d.tags.split(",")]
    positive, negative = sheet_prompt(d, "turnaround")
    fixed_negative = {t.strip() for t in negative.split(",")}
    assert len(tags) > 2 and tags[:2] == ["mature", "adult"] and len(tags) == len(set(tags))
    assert not (set(tags) & fixed_negative) and "young" not in d.tags and "old" not in tags


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


def test_signature_item_shows_on_body_views_and_is_left_out_of_close_ups():
    answers = ca.clean_answers(good(signature="katana"))
    d = ca.to_design(answers, "player", 1)
    assert "katana" in sheet_prompt(d, "turnaround")[0]   # the colour guide is cut from the turnaround
    close = ca.to_design(answers, "player", 1, close_up=True)
    assert all("katana" not in pos and "katana" not in neg for _, pos, neg in expression_prompts(close))


def test_close_up_keeps_an_outfit_tag_that_matches_the_signature():
    close = ca.to_design(ca.clean_answers(good(signature="red scarf", outfit="red scarf")), "player", 1, close_up=True)
    assert "red scarf" in close.tags


@pytest.mark.parametrize("kind", ["player", "npc", "ai"])
def test_the_design_is_a_valid_character_with_a_source_naming_the_kind(kind):
    d = ca.to_design(ca.clean_answers(good()), kind, 7)
    validate(d)
    assert d.kind == "character" and d.source == f"creator:{kind}" and d.name == "Vex"


MUST_REFUSE = ["young_woman", "petite_body", "12yo_girl", "17-year-old", "17 y.o.", "sixteen years old", "aged 12", "childlike",
               "preteen", "teenaged", "lolis", "lolicon", "shotacon", "high school student", "school uniform", "flat chest",
               "aged down", "chibi", "baby face", "unclothed", "no clothes", "without clothing", "see-through", "exposed breasts",
               "fellatio", "testicles", "bondage", "questionable", "rating:questionable", "n.u.d.e",
               "nu\u200bde", "\uff4e\uff55\uff44\uff45", "nud\u0435",
               "n-u-d-e", "n_u_d_e", "n u d e", "seventeen-year-old", "age: 15", "9 years of age", "17 y/o", "(young:1.3) woman"]
PROMPT_FIELDS = ["hair", "eyes", "skin", "build", "face_extras", "outfit", "colours", "marks", "chrome", "signature", "extra"]


@pytest.mark.parametrize("text", MUST_REFUSE)
def test_common_forms_are_refused_in_tag_fields(text):
    with pytest.raises(ca.BadAnswers):
        ca.clean_answers(good(outfit=text))


@pytest.mark.parametrize("field", [*PROMPT_FIELDS, "personality", "world_role", "home"])
def test_every_tag_field_is_screened_the_same_way(field):
    for text in ("young_woman", "\uff4e\uff55\uff44\uff45", "nud\u0435"):
        with pytest.raises(ca.BadAnswers):
            ca.clean_answers(good(**{field: text}))


@pytest.mark.parametrize("text", ["nude", "young_woman", "12yo_girl", "n.u.d.e", "nu\u200bde", "\uff4e\uff55\uff44\uff45", "lolicon"])
@pytest.mark.parametrize("field", ["name", "backstory"])
def test_name_and_backstory_are_screened_too(field, text):
    with pytest.raises(ca.BadAnswers):
        ca.clean_answers(good(**{field: text}))


def test_notes_are_screened_the_same_way():
    for text in MUST_REFUSE:
        with pytest.raises(ca.BadAnswers):
            ca.clean_text(text, "the note")


@pytest.mark.parametrize("text", ["35 years old", "aged 35", "age 40", "18 years old", "thirty-five years old", "twenty one years old",
                                  "old leather coat", "scar from 5 years ago", "5 year veteran", "exposed wiring", "baby blue jacket",
                                  "mid-length hair", "red-eyed", "St. Mark's cross", "corporate attire", "no sleeves"])
def test_ordinary_text_and_adult_ages_are_not_refused(text):
    assert ca.clean_answers(good(outfit=text))["outfit"]


@pytest.mark.parametrize("field, value", [("name", "\u591c\u6708"), ("name", "Ren\u00e9e"), ("backstory", "fled \u6771\u4eac at night")])
def test_name_and_backstory_can_use_any_letters(field, value):
    assert ca.clean_answers(good(**{field: value}))[field] == value


def test_tag_fields_refuse_other_alphabets_with_a_reason():
    for value in ("\u591c\u6708", "caf\u00e9 apron", "n\u0338ude"):
        with pytest.raises(ca.BadAnswers, match="English"):
            ca.clean_answers(good(outfit=value))


def test_tag_fields_are_stored_normalised_but_names_keep_their_hyphens():
    got = ca.clean_answers(good(name="Mei-Lan", hair="silver_hair, mid-length", outfit="\uff54\uff52\uff45\uff4e\uff43\uff48 co\u200bat"))
    assert got["name"] == "Mei-Lan" and got["hair"] == "silver hair, mid length" and got["outfit"] == "trench coat"


@pytest.mark.parametrize("text, kept", [("embedding:easynegative, red coat", "red coat"), ("EMBEDDING:bad_thing", ""),
                                        ("(embedding:x:1.2), red coat", "red coat"), ("embed\u200bding:x red coat", "red coat")])
def test_embedding_syntax_is_stripped(text, kept):
    assert ca.clean_answers(good(outfit=text)).get("outfit", "") == kept


def test_fixed_negative_has_questionable_and_the_sexual_terms():
    d = ca.to_design(ca.clean_answers(good()), "player", 1)
    for word in ("questionable", "fellatio", "testicles", "bondage", "unclothed", "exposed breasts"):
        assert word in d.negative
        assert word in sheet_prompt(d, "turnaround")[1] and word in expression_prompts(d)[0][2]


def test_shared_image_studio_list_is_left_alone():
    assert st.refused_terms("young woman") == [] and st.refused_terms("school uniform") == []


def test_fifty_plus_is_never_sexualised():
    answers = ca.clean_answers(good(age="50+"))
    d = ca.to_design(answers, "player", 1)
    for word in ("cleavage", "revealing clothes", "lingerie", "swimsuit", "suggestive", "seductive"):
        assert word in d.negative
    positive = sheet_prompt(d, "turnaround")[0]
    assert "sensitive" in positive and "sensitive" not in ca.rated(positive, answers) and ", safe" in ca.rated(positive, answers)
    assert ca.rated(positive, ca.clean_answers(good(age="40s"))) == positive
    assert "cleavage" not in ca.to_design(ca.clean_answers(good(age="40s")), "player", 1).negative


@pytest.mark.parametrize("field", ["outfit", "extra", "build", "signature"])
@pytest.mark.parametrize("word", ["lingerie", "cleavage", "bikini", "revealing dress", "large breasts", "sexy"])
def test_fifty_plus_cant_ask_for_revealing_tags(field, word):
    with pytest.raises(ca.BadAnswers, match="50"):
        ca.clean_answers(good(age="50+", **{field: word}))
    assert ca.clean_answers(good(age="40s", **{field: word}))[field]


def test_fifty_plus_notes_are_held_to_the_same_rule():
    answers = ca.clean_answers(good(age="50+"))
    with pytest.raises(ca.BadAnswers, match="50"):
        ca.clean_note("lingerie", answers)
    assert ca.clean_note("(red scarf:1.2)", answers) == "red scarf"
    assert ca.clean_note("lingerie", ca.clean_answers(good())) == "lingerie"


def test_adult_negatives_are_applied():
    negative = sheet_prompt(ca.to_design(ca.clean_answers(good()), "player", 1), "turnaround")[1]
    assert "loli" in negative and "nude" in negative and "young" in negative
