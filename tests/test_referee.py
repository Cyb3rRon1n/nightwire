import json

import pytest

from engine.character import CharacterSheet
from engine.chrome import install_chrome
from engine.debt import SHELL
from engine.session import Session
from narrator.referee import apply_verdict, build_questions, build_schema, run_referee, validate_verdict


def _session(**kw) -> Session:
    s = Session(session_id="s1")
    defaults = dict(player_id="p1", name="Rook", role="solo", lifepath="streetkid", attributes={"body": 12}, humanity=50)
    defaults.update(kw)
    s.characters["p1"] = CharacterSheet(**defaults)
    return s


def test_human_with_no_debt_is_only_asked_about_human_moments_location_and_leads():
    assert list(build_questions(_session(), "p1")) == ["human_moment", "moved_to", "new_lead"]


def test_conditional_questions_follow_state():
    s = _session(lifepath="tsukumogami", installments_owed=4, pending_repo="kagerou", throttled="kagerou")
    assert set(build_questions(s, "p1")) == {"human_moment", "moved_to", "new_lead", "acted_as_machine", "gave_up_repo_item",
                                             "gig_paid_out", "hara_unlocked_chrome"}
    bodiless = _session(lifepath="tsukumogami", installments_owed=4, bodiless=True)
    assert set(build_questions(bodiless, "p1")) == {"human_moment", "moved_to", "new_lead", "acted_as_machine", "got_new_shell"}


def test_schema_requires_every_question():
    schema = build_schema({"human_moment": "q", "gig_paid_out": "q"})
    assert schema["required"] == ["human_moment_quote", "human_moment", "gig_paid_out"]
    assert schema["properties"]["human_moment"]["enum"] == ["none", "small", "big"]
    assert schema["properties"]["gig_paid_out"]["type"] == "boolean"
    assert schema["additionalProperties"] is False


def test_validate_rejects_missing_or_wrong_types():
    q = {"human_moment": "q", "gig_paid_out": "q"}
    validate_verdict({"human_moment_quote": "", "human_moment": "small", "gig_paid_out": False}, q)
    for bad in ({"human_moment_quote": "", "human_moment": "small"},
                {"human_moment_quote": "", "human_moment": "huge", "gig_paid_out": False},
                {"human_moment_quote": "", "human_moment": "small", "gig_paid_out": "yes"},
                {"human_moment_quote": 3, "human_moment": "small", "gig_paid_out": False}):
        with pytest.raises(ValueError):
            validate_verdict(bad, q)


def test_human_moment_gains_and_machine_act_loses():
    s = _session()
    apply_verdict(s, "p1", {"human_moment": "big"})
    assert s.characters["p1"].humanity == 54
    t = _session(lifepath="tsukumogami", humanity=30)
    apply_verdict(t, "p1", {"human_moment": "small", "acted_as_machine": "big"})
    assert t.characters["p1"].humanity == 28
    assert "[selfhood: -2]" in t.log


def test_none_and_false_change_nothing():
    s = _session(installments_owed=4)
    apply_verdict(s, "p1", {"human_moment": "none", "gig_paid_out": False})
    assert s.characters["p1"].humanity == 50 and s.characters["p1"].installments_owed == 4 and s.log == []


def test_gave_up_repo_item_repossesses_with_torite_log():
    s = _session()
    install_chrome(s.characters["p1"], "kagerou")
    s.characters["p1"].pending_repo = "kagerou"
    apply_verdict(s, "p1", {"human_moment": "none", "gave_up_repo_item": True, "gig_paid_out": False})
    assert "kagerou" not in s.characters["p1"].chrome
    assert "[torite: Saeko's crew took Rook's Kagerou]" in s.log


def test_shell_repo_logs_the_drop():
    s = _session(name="Hachi", lifepath="tsukumogami", humanity=30, installments_owed=4, pending_repo=SHELL)
    apply_verdict(s, "p1", {"human_moment": "none", "acted_as_machine": "none", "gave_up_repo_item": True, "gig_paid_out": False})
    assert s.characters["p1"].bodiless
    assert "[torite: Saeko's crew took Hachi's shell - Hachi drops into the nearest machine]" in s.log


def test_repo_and_unthrottle_run_before_payment():
    s = _session()
    c = s.characters["p1"]
    install_chrome(c, "kagerou")
    c.throttled = c.pending_repo = "kagerou"
    apply_verdict(s, "p1", {"human_moment": "none", "gave_up_repo_item": True, "gig_paid_out": True,
                            "hara_unlocked_chrome": False})
    assert "kagerou" not in c.chrome and c.installments_owed == 4


def test_unthrottle_adds_hara_objective_once():
    s = _session()
    c = s.characters["p1"]
    install_chrome(c, "kagerou")
    for _ in range(2):
        c.throttled = "kagerou"
        apply_verdict(s, "p1", {"human_moment": "none", "gig_paid_out": False, "hara_unlocked_chrome": True})
    assert c.throttled is None
    assert s.active_objectives.count("Owe Old Hara a favor") == 1


def test_new_shell_wakes_them():
    s = _session(name="Hachi", lifepath="tsukumogami", bodiless=True)
    apply_verdict(s, "p1", {"human_moment": "none", "acted_as_machine": "none", "got_new_shell": True})
    assert not s.characters["p1"].bodiless
    assert "[utsusemi: Hachi wakes in a new shell]" in s.log


def test_gig_paid_out_pays_one():
    s = _session(installments_owed=4)
    apply_verdict(s, "p1", {"human_moment": "none", "gig_paid_out": True})
    assert s.characters["p1"].installments_owed == 3


class _Client:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, []
    async def judge(self, messages, schema):
        self.calls.append((messages, schema))
        if self.error:
            raise self.error
        return self.answer


async def test_run_referee_applies_a_valid_verdict_and_sends_context():
    s = _session(installments_owed=4)
    client = _Client({"human_moment_quote": "pays you in cash", "human_moment": "small", "gig_paid_out": True})
    await run_referee(s, client, "p1", "I finish Arakawa's job.", "Arakawa pays you in cash.")
    assert s.characters["p1"].humanity == 52 and s.characters["p1"].installments_owed == 3
    prompt = json.dumps(client.calls[0][0])
    assert "Arakawa pays you in cash." in prompt and "owes 4" in prompt


def test_level_answers_need_a_quote_field_before_them():
    schema = build_schema({"human_moment": "q", "gig_paid_out": "q"})
    assert list(schema["properties"]) == ["human_moment_quote", "human_moment", "gig_paid_out"]
    assert schema["required"] == ["human_moment_quote", "human_moment", "gig_paid_out"]
    with pytest.raises(ValueError):
        validate_verdict({"human_moment": "small", "gig_paid_out": False}, {"human_moment": "q", "gig_paid_out": "q"})


async def test_a_moment_backed_by_a_real_quote_counts():
    s = _session()
    client = _Client({"human_moment_quote": "You share  your noodles", "human_moment": "small"})
    await run_referee(s, client, "p1", "I sit with the kid.", "You share your noodles with the kid. She grins.")
    assert s.characters["p1"].humanity == 52


async def test_a_moment_without_a_matching_quote_is_dropped():
    # Phase 18 live: plain stealth and jump turns earned +2 "human moments".
    for quote in ("", "you comfort the old man", "  "):
        s = _session()
        client = _Client({"human_moment_quote": quote, "human_moment": "small"})
        await run_referee(s, client, "p1", "I sneak past the guard.", "You slip past the guard unseen.")
        assert s.characters["p1"].humanity == 50
        assert "[referee: human_moment had no quote from the scene, ignored]" in s.log


async def test_acting_as_a_machine_needs_the_players_own_words():
    # Live 2026-11-06: the referee quoted the narrator's description of a roof climb as "big" machine behaviour.
    machine = {"human_moment_quote": "", "human_moment": "none"}
    narration = "The rain slicks the roof tiles. You climb onto the roof of the izakaya."
    s = _session(lifepath="tsukumogami", humanity=30)
    await run_referee(s, _Client({**machine, "acted_as_machine_quote": "You climb onto the roof of the izakaya.",
                                  "acted_as_machine": "big"}), "p1", "I climb onto the roof.", narration)
    assert s.characters["p1"].humanity == 30
    assert "[referee: acted_as_machine had no quote from the player's action, ignored]" in s.log
    t = _session(lifepath="tsukumogami", humanity=30)
    await run_referee(t, _Client({**machine, "acted_as_machine_quote": "I tell her my owner's script says pay up",
                                  "acted_as_machine": "small"}), "p1", "I tell her my owner's script says pay up.", "She stares.")
    assert t.characters["p1"].humanity == 28


async def test_question_rules_out_skill_checks():
    s = _session()
    client = _Client({"human_moment_quote": "", "human_moment": "none"})
    await run_referee(s, client, "p1", "a", "b")
    assert "Sneaking" in json.dumps(client.calls[0][0])


def test_machine_question_rules_out_skill_checks_and_dice():
    # Live 2026-11-06: a plain roof climb cost Hachi selfhood, quoting the dice line as "cold calculation".
    q = build_questions(_session(lifepath="tsukumogami", humanity=30), "p1")["acted_as_machine"]
    assert "Sneaking" in q and "dice" in q


async def test_run_referee_failure_logs_and_changes_nothing():
    for client in (_Client(error=ValueError("bad json")), _Client({"human_moment": "small"})):
        s = _session(installments_owed=4)
        await run_referee(s, client, "p1", "a", "b")
        assert s.characters["p1"].humanity == 50
        assert any(line.startswith("[referee error: ") for line in s.log)


def test_unthrottle_runs_before_payment():
    s = _session()
    c = s.characters["p1"]
    install_chrome(c, "kagerou")
    c.throttled = "kagerou"
    apply_verdict(s, "p1", {"human_moment": "none", "gig_paid_out": True, "hara_unlocked_chrome": True})
    assert c.throttled is None and c.installments_owed == 4
    assert s.active_objectives.count("Owe Old Hara a favor") == 1


def test_selfhood_gain_is_logged_and_human_gain_is_not():
    t = _session(lifepath="tsukumogami", humanity=30)
    apply_verdict(t, "p1", {"human_moment": "big", "acted_as_machine": "none"})
    assert any(line.startswith("[selfhood: +") for line in t.log)
    h = _session()
    apply_verdict(h, "p1", {"human_moment": "big"})
    assert not any(line.startswith("[selfhood") for line in h.log)


def test_selfhood_log_records_applied_change_not_requested():
    t = _session(lifepath="tsukumogami", humanity=2)
    apply_verdict(t, "p1", {"human_moment": "none", "acted_as_machine": "big"})
    assert "[selfhood: -2]" in t.log
    t.log.clear()
    apply_verdict(t, "p1", {"human_moment": "none", "acted_as_machine": "big"})  # already 0
    assert not any(line.startswith("[selfhood") for line in t.log)


async def test_arriving_somewhere_named_in_the_scene_sets_the_location():
    # Live 2026-11-06: the narrator spent its one tool on remember_npc and never set the izakaya as the location.
    s = _session()
    await run_referee(s, _Client({"moved_to": "Mama Sato's izakaya", "human_moment_quote": "", "human_moment": "none"}),
                      "p1", "I duck into Mama Sato's izakaya out of the rain.", "The door swings shut behind you.")
    assert s.location == "Mama Sato's izakaya"


async def test_a_location_not_named_in_the_scene_is_ignored():
    s = _session(); s.location = "Ikebe Low"
    await run_referee(s, _Client({"moved_to": "Hoshikawa penthouse", "human_moment_quote": "", "human_moment": "none"}),
                      "p1", "I wait in the alley.", "Rain drips from the awning.")
    assert s.location == "Ikebe Low"
    assert "[referee: moved_to had no match in the scene, ignored]" in s.log


async def test_no_move_keeps_the_location():
    s = _session(); s.location = "Ikebe Low"
    await run_referee(s, _Client({"moved_to": "", "human_moment_quote": "", "human_moment": "none"}), "p1", "I wait.", "Rain.")
    assert s.location == "Ikebe Low"


def test_location_question_is_always_asked_as_text():
    q = build_questions(_session(), "p1")
    assert "moved_to" in q and build_schema(q)["properties"]["moved_to"] == {"type": "string", "maxLength": 60}


async def test_an_npc_naming_a_place_does_not_move_the_player():
    # Dry run 2026-11-06: Mama Sato asking "What brings you to Ikebe?" moved the player out of her izakaya.
    s = _session(); s.location = "Mama Sato's izakaya"
    await run_referee(s, _Client({"moved_to": "Ikebe", "human_moment_quote": "", "human_moment": "none"}),
                      "p1", "👍", "The lanterns sway.\nMama Sato: What brings you to Ikebe again, child?")
    assert s.location == "Mama Sato's izakaya"


async def test_the_narrator_describing_arrival_still_moves_the_player():
    s = _session(); s.location = "Ikebe Low"
    await run_referee(s, _Client({"moved_to": "the docks", "human_moment_quote": "", "human_moment": "none"}),
                      "p1", "I head out.", "You reach the docks as the cranes groan.\nHachi: Late again.")
    assert s.location == "Kuroshio Docks"  # the known place, by its own name


def test_gig_paid_out_texts_from_jun_and_raises_trust():
    from engine import phone
    s = _session(installments_owed=3)
    apply_verdict(s, "p1", {"human_moment": "none", "gig_paid_out": True})
    p = phone.phone_of(s, "p1")
    assert [m["text"] for m in p["threads"]["Jun Arakawa"]] == ["Money's in. Clean work."]
    assert phone.unread(s, "p1")["Jun Arakawa"] == 1
    assert p["contacts"]["Jun Arakawa"]["trust"] == phone.START_TRUST.get("fixer", 2.0) + 0.5


# --- trust moves (phone) ---

from engine import phone as _phone

_NONE = {"human_moment_quote": "", "human_moment": "none"}


def _phone_session(*contacts):
    s = _session()
    for name, role in contacts:
        _phone.add_contact(s, "p1", name, role)
    return s


async def _trust_turn(s, field, name, narration="Saeko Kirigaya stares at you."):
    await run_referee(s, _Client({**_NONE, "moved_to": "", field: name}), "p1", "I talk.", narration)


def _c(s, name):
    return _phone.phone_of(s, "p1")["contacts"][name]


def test_trust_questions_absent_without_contacts_present_with():
    assert not {"kept_promise_to", "helped_at_a_cost", "broke_promise_to", "lie_discovered_by"} & set(build_questions(_session(), "p1"))
    q = build_questions(_phone_session(("Saeko Kirigaya", "fixer")), "p1")
    assert {"kept_promise_to", "helped_at_a_cost", "broke_promise_to", "lie_discovered_by"} <= set(q)
    assert build_schema(q)["properties"]["lie_discovered_by"]["type"] == "string"


async def test_kept_promise_and_help_raise_trust_broke_lowers():
    s = _phone_session(("Saeko Kirigaya", "fixer"))
    t0 = _c(s, "Saeko Kirigaya")["trust"]
    await _trust_turn(s, "kept_promise_to", "Saeko Kirigaya")
    await _trust_turn(s, "helped_at_a_cost", "Saeko Kirigaya")
    assert _c(s, "Saeko Kirigaya")["trust"] > t0
    t1 = _c(s, "Saeko Kirigaya")["trust"]
    await _trust_turn(s, "broke_promise_to", "Saeko Kirigaya")
    assert _c(s, "Saeko Kirigaya")["trust"] == t1 - 1


async def test_lie_discovered_lowers_trust_goes_cold_and_tells_narrator():
    s = _phone_session(("Saeko Kirigaya", "fixer"))
    c = _c(s, "Saeko Kirigaya"); c["trust"] = 3.0
    await _trust_turn(s, "lie_discovered_by", "Saeko")
    assert c["trust"] == 2.0 and c["cold_until"] == 3
    assert "Saeko Kirigaya knows Rook lied to them." in s.pending_world_events


async def test_lie_costs_two_at_high_trust_or_family():
    s = _phone_session(("Saeko Kirigaya", "fixer"), ("Mom", "family"))
    _c(s, "Saeko Kirigaya")["trust"] = 4.0
    await _trust_turn(s, "lie_discovered_by", "Saeko Kirigaya")
    assert _c(s, "Saeko Kirigaya")["trust"] == 2.0
    _c(s, "Mom")["trust"] = 3.0
    await _trust_turn(s, "lie_discovered_by", "Mom", "Mom frowns.")
    assert _c(s, "Mom")["trust"] == 1.0


async def test_lie_never_drops_below_one_and_low_trust_unchanged():
    s = _phone_session(("Saeko Kirigaya", "fixer"))
    c = _c(s, "Saeko Kirigaya"); c["trust"] = 1.0
    await _trust_turn(s, "lie_discovered_by", "Saeko Kirigaya")
    assert c["trust"] == 1.0
    c["trust"] = 0.5
    await _trust_turn(s, "lie_discovered_by", "Saeko Kirigaya")
    assert c["trust"] == 0.5


async def test_rival_unchanged_by_lie_no_cold_spell():
    s = _phone_session(("Saeko Kirigaya", "rival"))
    c = _c(s, "Saeko Kirigaya"); before = c["trust"]
    await _trust_turn(s, "lie_discovered_by", "Saeko Kirigaya")
    assert c["trust"] == before and c["cold_until"] == -1
    assert not s.pending_world_events


async def test_ungrounded_trust_name_is_ignored_and_logged():
    s = _phone_session(("Saeko Kirigaya", "fixer"))
    c = _c(s, "Saeko Kirigaya"); before = c["trust"]
    await _trust_turn(s, "kept_promise_to", "Saeko Kirigaya", "Rain falls.")
    assert c["trust"] == before
    assert "[referee: kept_promise_to had no match in the scene, ignored]" in s.log


async def test_short_name_matches_one_contact_but_shared_word_matches_none():
    s = _phone_session(("Saeko Kirigaya", "fixer"), ("Saeko Mori", "friend"))
    t = {n: _c(s, n)["trust"] for n in ("Saeko Kirigaya", "Saeko Mori")}
    await _trust_turn(s, "broke_promise_to", "Saeko", "Saeko glares.")
    assert {n: _c(s, n)["trust"] for n in t} == t
    await _trust_turn(s, "broke_promise_to", "Kirigaya", "Kirigaya glares.")
    assert _c(s, "Saeko Kirigaya")["trust"] == t["Saeko Kirigaya"] - 1


async def test_an_unknown_place_does_not_move_the_player():
    s = _session(); s.location = "Ikebe Low"
    await run_referee(s, _Client({"moved_to": "the cramped bathroom", "human_moment_quote": "", "human_moment": "none"}),
                      "p1", "I duck into the cramped bathroom.", "The cramped bathroom smells of bleach.")
    assert s.location == "Ikebe Low"
    assert "[referee: moved_to is not a known place, ignored]" in s.log


async def test_a_short_name_in_the_scene_still_counts():
    # Playthrough 2026-11-07: "The izakaya is warm" didn't count for moved_to "Mama Sato's izakaya".
    s = _session(); s.location = "Ikebe Low"
    await run_referee(s, _Client({"moved_to": "Mama Sato's izakaya", "human_moment_quote": "", "human_moment": "none"}),
                      "p1", "I go inside with her.", "The izakaya is warm, the air thick with soy.")
    assert s.location == "Mama Sato's izakaya"


async def test_a_lead_from_the_scene_becomes_an_objective():
    # Playthrough 2026-11-07: objectives stayed empty through a whole mystery.
    s = _session(); s.location = "Ikebe Low"
    await run_referee(s, _Client({"moved_to": "", "new_lead": "Ask Jun about the Yomi Line data", "human_moment_quote": "",
                                  "human_moment": "none"}),
                      "p1", "I ask who wants me dead.", "Mama Sato: Talk to Jun. It's about what you found on the Yomi Line.")
    assert s.active_objectives == ["Ask Jun about the Yomi Line data"]


async def test_an_invented_lead_is_ignored():
    s = _session()
    await run_referee(s, _Client({"moved_to": "", "new_lead": "Find the safehouse", "human_moment_quote": "",
                                  "human_moment": "none"}), "p1", "I wait.", "Rain falls.")
    assert s.active_objectives == [] and "[referee: new_lead names nothing in the scene, ignored]" in s.log


async def test_a_finished_objective_is_removed():
    s = _session(); s.active_objectives = ["Go inside and talk to Mama Sato", "Pick up Jun's case"]
    await run_referee(s, _Client({"moved_to": "", "new_lead": "", "objective_done": "Go inside and talk to Mama Sato",
                                  "human_moment_quote": "", "human_moment": "none"}),
                      "p1", "I go in and talk to Mama Sato.", "Mama Sato: Sit, child.")
    assert s.active_objectives == ["Pick up Jun's case"]
