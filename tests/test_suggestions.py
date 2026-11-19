import json

from engine.character import CharacterSheet
from engine.persistence import JSONFileSessionStore
from engine.session import Session
from narrator.suggestions import LOOK_AROUND, SCHEMA, check_chips, suggest


def _rin(**kw):
    return CharacterSheet(player_id="p1", name="Rin", role="netrunner", lifepath="streetkid",
                          skills={"hacking": 2, "persuasion": 1}, **kw)


def _tagged(text, skill, attribute="presence", stakes="normal"):
    return {"text": text, "skill": skill, "attribute": attribute, "stakes": stakes}


def _plain(text):
    return {"text": text, "skill": "none", "attribute": "none", "stakes": "none"}


def test_a_good_set_keeps_one_plain_and_two_tagged_with_real_chances():
    chips = check_chips([_plain("I ask Mama Sato about the collector."),
                         _tagged("I talk the doorman down.", "persuasion"),
                         _tagged("I slice the door lock.", "hacking", "tech", "high")], _rin(), [])
    assert [c["text"] for c in chips] == ["I ask Mama Sato about the collector.", "I talk the doorman down.",
                                         "I slice the door lock."]
    assert chips[0]["skill"] is None
    assert chips[1] | {"id": "x"} == {"id": "x", "text": "I talk the doorman down.", "skill": "persuasion",
                                      "attribute": "presence", "stakes": "normal", "difficulty": "moderate"}
    assert chips[2]["difficulty"] == "hard" and chips[2]["attribute"] == "tech"
    assert len({c["id"] for c in chips}) == 3


def test_a_bad_tag_turns_the_chip_plain_and_an_empty_chip_is_dropped():
    chips = check_chips([_tagged("I juggle the knives.", "juggling"), {"text": "  "}], _rin(), [])
    assert [(c["text"], c["skill"]) for c in chips] == [("I juggle the knives.", None)]


def test_no_plain_chip_adds_look_around_and_keeps_two_tagged():
    raw = [_tagged("I talk my way in.", "persuasion"), _tagged("I hack the camera.", "hacking", "tech"),
           _tagged("I charm the guard.", "persuasion")]
    chips = check_chips(raw, _rin(), [])
    assert [c["text"] for c in chips] == [LOOK_AROUND, "I talk my way in.", "I hack the camera."]


def test_the_difficulty_cap_is_applied_when_the_chip_is_made():
    chips = check_chips([_plain("I wait."), _tagged("I jump the gap.", "athletics", "body", "high")],
                        _rin(), ["high", "high"])
    assert chips[1]["stakes"] == "normal" and chips[1]["difficulty"] == "moderate"


def test_the_attribute_is_corrected_to_a_sensible_pair():
    chips = check_chips([_plain("I wait."), _tagged("I sneak past.", "stealth", "presence")], _rin(), [])
    assert chips[1]["attribute"] != "presence"  # ruleset/skills.py: no Stealth (Presence)


def test_a_bodiless_character_gets_no_physical_chips():
    ghost = _rin()
    ghost.bodiless = True
    chips = check_chips([_plain("I listen."), _tagged("I climb the crane.", "athletics", "body")], ghost, [])
    assert [c["text"] for c in chips] == ["I listen."]


def test_junk_answers_give_no_chips():
    assert check_chips(False, _rin(), []) == []
    assert check_chips([], _rin(), []) == []
    assert check_chips(["nope", {"text": ""}], _rin(), []) == []


async def test_suggest_asks_the_judge_with_the_scene_and_returns_the_chips():
    seen = {}

    class Judge:
        async def judge(self, messages, schema):
            seen.update(messages=messages, schema=schema)
            return {"chips": [_plain("I look at the menu.")]}

    raw = await suggest(Judge(), ["Mama Sato wipes the counter."], "Ikebe Low", _rin())
    assert raw == [_plain("I look at the menu.")]
    assert seen["schema"] is SCHEMA
    prompt = seen["messages"][-1]["content"]
    assert "Mama Sato wipes the counter." in prompt and "Ikebe Low" in prompt and "hacking" in prompt


def test_suggestions_are_saved_and_loaded(tmp_path):
    store = JSONFileSessionStore(tmp_path)
    session = Session(session_id="s1", suggestions={"p1": [{"id": "a", "text": "I wait."}]})
    store.save(session)
    assert store.load("s1").suggestions == {"p1": [{"id": "a", "text": "I wait."}]}
    json.dumps(SCHEMA)  # the schema must be plain JSON for Ollama


def test_a_chip_naming_a_place_or_person_the_scene_never_showed_is_dropped():
    # Chips soak 2026-11-18: "I slip into the clinic's back alley" from inside the izakaya.
    scene = "Mama Sato pours tea behind the izakaya counter."
    chips = check_chips([_plain("I ask Mama Sato about the collector."),
                         _tagged("I slip into the clinic's back alley.", "stealth", "reflexes"),
                         _tagged("I ask Old Hara for a discount.", "persuasion")], _rin(), [], scene)
    assert [c["text"] for c in chips] == ["I ask Mama Sato about the collector."]


def test_without_a_scene_nothing_is_dropped_for_names():
    chips = check_chips([_plain("I talk to Old Hara.")], _rin(), [])
    assert [c["text"] for c in chips] == ["I talk to Old Hara."]
