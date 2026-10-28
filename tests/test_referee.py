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


def test_human_with_no_debt_is_only_asked_about_human_moments():
    assert list(build_questions(_session(), "p1")) == ["human_moment"]


def test_conditional_questions_follow_state():
    s = _session(lifepath="tsukumogami", installments_owed=4, pending_repo="kagerou", throttled="kagerou")
    assert set(build_questions(s, "p1")) == {"human_moment", "acted_as_machine", "gave_up_repo_item",
                                             "gig_paid_out", "hara_unlocked_chrome"}
    bodiless = _session(lifepath="tsukumogami", installments_owed=4, bodiless=True)
    assert set(build_questions(bodiless, "p1")) == {"human_moment", "acted_as_machine", "got_new_shell"}


def test_schema_requires_every_question():
    schema = build_schema({"human_moment": "q", "gig_paid_out": "q"})
    assert schema["required"] == ["human_moment", "gig_paid_out"]
    assert schema["properties"]["human_moment"]["enum"] == ["none", "small", "big"]
    assert schema["properties"]["gig_paid_out"]["type"] == "boolean"
    assert schema["additionalProperties"] is False


def test_validate_rejects_missing_or_wrong_types():
    q = {"human_moment": "q", "gig_paid_out": "q"}
    validate_verdict({"human_moment": "small", "gig_paid_out": False}, q)
    for bad in ({"human_moment": "small"}, {"human_moment": "huge", "gig_paid_out": False},
                {"human_moment": "small", "gig_paid_out": "yes"}):
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
    client = _Client({"human_moment": "small", "gig_paid_out": True})
    await run_referee(s, client, "p1", "I finish Arakawa's job.", "Arakawa pays you in cash.")
    assert s.characters["p1"].humanity == 52 and s.characters["p1"].installments_owed == 3
    prompt = json.dumps(client.calls[0][0])
    assert "Arakawa pays you in cash." in prompt and "owes 4" in prompt


async def test_run_referee_failure_logs_and_changes_nothing():
    for client in (_Client(error=ValueError("bad json")), _Client({"human_moment": "small"})):
        s = _session(installments_owed=4)
        await run_referee(s, client, "p1", "a", "b")
        assert s.characters["p1"].humanity == 50
        assert any(line.startswith("[referee error: ") for line in s.log)
