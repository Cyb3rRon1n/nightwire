import pytest

from engine.character import CharacterSheet
from engine.chrome import install_chrome
from engine.debt import active_chrome, pay_installment, repossess, tick_debt, unthrottle


def _rook():
    c = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid", attributes={"body": 10})
    install_chrome(c, "lacquer_skin")  # owes 3, armor 10
    install_chrome(c, "kagerou")       # owes 8 total
    return c


def _tick(c, n):
    events = []
    for _ in range(n):
        events += tick_debt(c)
    return events


def test_no_tick_without_debt():
    c = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid")
    assert _tick(c, 100) == [] and c.repo_clock == 0


def test_clock_ticks_every_ten_and_strike_one_is_a_notice():
    c = _rook()
    assert _tick(c, 9) == [] and c.repo_clock == 0
    assert _tick(c, 1) == [] and c.repo_clock == 1
    events = _tick(c, 50)
    assert c.repo_clock == 0 and c.repo_strikes == 1
    assert events == ["Hoshikawa sends Rook a polite final notice; Saeko Kirigaya's torite crew has been asking about Rook."]


def test_strike_two_throttles_newest_and_removes_stats():
    c = _rook()
    c.chrome = ["kagerou", "lacquer_skin"]  # make lacquer_skin the newest
    events = _tick(c, 120)
    assert c.repo_strikes == 2 and c.throttled == "lacquer_skin" and c.armor == 0
    assert events[-1] == "Rook's Lacquer skin locks up: remote-throttled by Hoshikawa for missed payments."
    assert active_chrome(c) == ["kagerou"]


def test_strike_three_targets_the_throttled_item():
    c = _rook()
    events = _tick(c, 180)
    assert c.repo_strikes == 3 and c.pending_repo == c.throttled == "kagerou"
    assert events[-1] == "Saeko Kirigaya's torite crew comes for Rook's Kagerou."


def test_strike_without_chrome_is_a_notice():
    c = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid", installments_owed=2)
    assert "final notice" in _tick(c, 120)[-1] and c.throttled is None


def test_payment_resets_unthrottles_and_clears_repo():
    c = _rook()
    c.chrome = ["kagerou", "lacquer_skin"]
    _tick(c, 185)
    pay_installment(c, 1)
    assert (c.installments_owed, c.repo_clock, c.repo_actions) == (7, 0, 0)
    assert c.throttled is None and c.pending_repo is None and c.armor == 10
    assert c.repo_strikes == 3  # still owes
    c.installments_owed = 1
    pay_installment(c, 1)
    assert c.installments_owed == 0 and c.repo_strikes == 0


def test_repossess_removes_pending_item_only():
    c = _rook()
    _tick(c, 180)
    removed = repossess(c)
    assert removed == "kagerou" and "kagerou" not in c.chrome and "lacquer_skin" in c.chrome
    assert c.pending_repo is None and c.throttled is None and c.installments_owed == 8
    with pytest.raises(ValueError, match="no repo"):
        repossess(c)


def test_unthrottle_restores_stats_keeps_debt():
    c = _rook()
    c.chrome = ["kagerou", "lacquer_skin"]
    _tick(c, 120)
    clock, owed = c.repo_clock, c.installments_owed
    unthrottle(c)
    assert c.throttled is None and c.armor == 10 and (c.repo_clock, c.installments_owed) == (clock, owed)
    with pytest.raises(ValueError, match="nothing is throttled"):
        unthrottle(c)


from engine.chrome import change_humanity
from engine.debt import SHELL, new_shell, repo_target_name


def _hachi(**kw):
    return CharacterSheet(player_id="p1", name="Hachi", role="fixer", lifepath="tsukumogami",
                          humanity=30, installments_owed=4, attributes={"body": 10}, **kw)


def _force_strike(c):
    c.repo_actions, c.repo_clock = 9, 5
    return tick_debt(c)


def test_chromeless_tsukumogami_strike_three_comes_for_the_shell():
    c = _hachi()
    _force_strike(c); _force_strike(c)
    assert c.pending_repo is None
    assert _force_strike(c) == ["Saeko Kirigaya's torite crew comes for Hachi's utsusemi shell."]
    assert c.pending_repo == SHELL


def test_tsukumogami_loses_chrome_before_the_shell():
    c = _hachi()
    install_chrome(c, "neon_ink")
    c.repo_strikes = 2
    _force_strike(c)
    assert c.pending_repo == "neon_ink"


def test_chromeless_human_strike_three_is_still_only_a_notice():
    c = CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid", installments_owed=3)
    c.repo_strikes = 2
    assert "final notice" in _force_strike(c)[0]
    assert c.pending_repo is None


def test_shell_repo_strips_chrome_and_leaves_them_bodiless():
    c = _hachi()
    install_chrome(c, "lacquer_skin")
    armor_before = c.armor
    c.pending_repo = SHELL
    assert repossess(c) == SHELL
    assert c.chrome == [] and c.armor == armor_before - 10
    assert c.bodiless and c.pending_repo is None and c.throttled is None
    assert c.humanity == 25


def test_awake_tsukumogami_loses_no_selfhood_on_shell_repo():
    c = _hachi()
    c.humanity = 85
    c.pending_repo = SHELL
    repossess(c)
    assert c.humanity == 85


def test_bodiless_pauses_the_repo_clock():
    c = _hachi(bodiless=True)
    assert _tick(c, 100) == [] and c.repo_clock == 0 and c.repo_actions == 0


def test_new_shell_requires_bodiless():
    with pytest.raises(ValueError, match="not bodiless"):
        new_shell(_hachi())


def test_new_shell_is_a_fresh_contract():
    c = _hachi(bodiless=True, repo_strikes=3, repo_clock=2, repo_actions=4)
    new_shell(c)
    assert not c.bodiless
    assert c.installments_owed == 8
    assert (c.repo_clock, c.repo_actions, c.repo_strikes) == (0, 0, 0)


def test_repo_target_name():
    assert repo_target_name(SHELL) == "utsusemi shell"
    assert repo_target_name("kagerou") == "Kagerou"
