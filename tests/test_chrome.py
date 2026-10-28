import pytest

from engine.character import CharacterSheet
from engine.chrome import change_humanity, install_chrome, remove_chrome, usable_overclocks


def _rook(**kw):
    return CharacterSheet(player_id="p1", name="Rook", role="solo", lifepath="streetkid", attributes={"body": 10}, **kw)


def test_install_applies_cost_stats_debt_and_order():
    rook = _rook()
    install_chrome(rook, "lacquer_skin")
    install_chrome(rook, "pain_editor")
    assert rook.chrome == ["lacquer_skin", "pain_editor"]
    assert rook.humanity == 100 - 6 - 5
    assert rook.armor == 10 and rook.max_health == 115
    assert rook.installments_owed == 3 + 3


def test_install_rejects_duplicate_full_slots_and_gone_too_far():
    rook = _rook()
    install_chrome(rook, "neon_ink")
    with pytest.raises(ValueError, match="already installed"):
        install_chrome(rook, "neon_ink")
    install_chrome(rook, "hawkeye_optics")
    install_chrome(rook, "silk_tongue")  # body 10 -> 3 slots, now full
    with pytest.raises(ValueError, match="no free chrome slot"):
        install_chrome(rook, "kumo_hand")
    gone = _rook(humanity=0, gone_too_far=True)
    with pytest.raises(ValueError, match="humanity"):
        install_chrome(gone, "neon_ink")
    with pytest.raises(ValueError, match="unknown chrome"):
        install_chrome(_rook(), "nope")


def test_remove_refunds_half_reverses_stats_keeps_debt():
    rook = _rook()
    install_chrome(rook, "pain_editor")  # 95 humanity, 115 max
    rook.health = 110
    remove_chrome(rook, "pain_editor")
    assert rook.chrome == [] and rook.humanity == 97  # +5 // 2
    assert rook.max_health == 100 and rook.health == 100
    assert rook.installments_owed == 3
    with pytest.raises(ValueError, match="not installed"):
        remove_chrome(rook, "pain_editor")


def test_change_humanity_clamps_locks_and_unlocks():
    rook = _rook(humanity=5)
    change_humanity(rook, -50)
    assert rook.humanity == 0 and rook.gone_too_far
    change_humanity(rook, 20)
    assert rook.gone_too_far  # 20 is not above 20
    change_humanity(rook, 1)
    assert not rook.gone_too_far
    change_humanity(rook, 500)
    assert rook.humanity == 100


def test_confrontation_fires_once_below_forty():
    rook = _rook(humanity=42)
    assert change_humanity(rook, -1) == []
    events = change_humanity(rook, -3)
    assert len(events) == 1 and "Rook" in events[0]
    assert change_humanity(rook, -10) == []


def test_usable_overclocks_by_skill_and_lock():
    rook = _rook()
    install_chrome(rook, "kagerou")
    install_chrome(rook, "yomi_jack")
    assert [o["id"] for o in usable_overclocks(rook, "stealth")] == ["kagerou"]
    assert [o["id"] for o in usable_overclocks(rook, "hacking")] == ["kagerou", "yomi_jack"]
    rook.gone_too_far = True
    assert usable_overclocks(rook, "hacking") == []


def test_remove_clears_matching_throttle_and_pending_repo():
    rook = _rook()
    install_chrome(rook, "kagerou")
    rook.throttled = rook.pending_repo = "kagerou"
    remove_chrome(rook, "kagerou")
    assert rook.throttled is None and rook.pending_repo is None


def test_usable_overclocks_omits_throttled():
    rook = _rook()
    install_chrome(rook, "kagerou")
    rook.throttled = "kagerou"
    assert usable_overclocks(rook, "hacking") == []


def _hachi(**kw):
    from engine.character import CharacterSheet
    return CharacterSheet(player_id="p1", name="Hachi", role="fixer", lifepath="tsukumogami",
                          humanity=20, attributes={"body": 10}, **kw)


def test_tsukumogami_never_gets_the_slipping_confrontation():
    from engine.chrome import change_humanity
    c = _hachi()
    assert change_humanity(c, -3) == [] and change_humanity(c, 2) == []
    assert c.slipping_warned is False


def test_tsukumogami_awake_event_fires_once_at_80():
    from engine.chrome import change_humanity
    c = _hachi()
    c.humanity = 78
    assert change_humanity(c, 1) == []
    assert change_humanity(c, 1) == ["Hachi feels it settle: they're someone now, not something."]
    assert c.awake_reached
    change_humanity(c, -10)
    assert change_humanity(c, 15) == []


def test_tsukumogami_chrome_costs_and_refunds_no_selfhood():
    from engine.chrome import install_chrome, remove_chrome
    c = _hachi()
    install_chrome(c, "kagerou")
    assert c.humanity == 20 and c.installments_owed == 5
    remove_chrome(c, "kagerou")
    assert c.humanity == 20


def test_bodiless_cannot_install_chrome():
    import pytest
    from engine.chrome import install_chrome
    c = _hachi(bodiless=True)
    with pytest.raises(ValueError, match="no shell to install chrome in"):
        install_chrome(c, "neon_ink")
