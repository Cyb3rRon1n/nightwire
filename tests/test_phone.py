from engine.character import CharacterSheet
from engine.session import Session
from engine import phone


def _s():
    s = Session(session_id="s")
    s.characters["p"] = CharacterSheet(player_id="p", name="Rin", role="netrunner", lifepath="streetkid")
    return s


def test_contacts_start_by_role():
    s = _s()
    assert phone.add_contact(s, "p", "Mama Sato")["trust"] == 2
    assert phone.add_contact(s, "p", "Goro", "enemy")["trust"] == 0
    assert phone.add_contact(s, "p", "Mom", "family")["trust"] == 3
    assert phone.add_contact(s, "p", "Mama Sato", "enemy")["role"] == "stranger"  # already there: unchanged


def test_delay_from_role_trust_and_pace():
    s = _s()
    saeko = phone.add_contact(s, "p", "Saeko Kirigaya", "creditor", pace=-1)   # 1 + (5-2) - 1 = 3
    assert phone.delay(saeko) == 3
    partner = phone.add_contact(s, "p", "Kaede Mori", "partner")                # 0 + (5-3) = 2
    partner["trust"] = 5
    assert phone.delay(partner) == 0
    enemy = phone.add_contact(s, "p", "Goro", "enemy")                           # 4 + 5 = 9 -> 6
    assert phone.delay(enemy) == 6


def test_trust_is_clamped_and_hard_to_raise_past_three():
    s = _s()
    c = phone.add_contact(s, "p", "Jun Arakawa", "fixer")
    for _ in range(10):
        phone.change_trust(c, 0.5)
    assert c["trust"] == 3          # small gains stop at 3
    phone.change_trust(c, 1)
    assert c["trust"] == 4          # a big event goes past
    phone.change_trust(c, -9)
    assert c["trust"] == 0


def test_tone_follows_trust_and_cold_spells():
    s = _s()
    c = phone.add_contact(s, "p", "Old Hara", "informant")
    assert phone.tone(c, 0) == "curt"
    c["trust"] = 4
    assert phone.tone(c, 0) == "warm"
    c["cold_until"] = 5
    assert phone.tone(c, 3) == "guarded"


def test_messages_arrive_when_due_and_count_as_unread():
    s = _s()
    phone.add_contact(s, "p", "Saeko Kirigaya", "creditor", pace=-1)
    phone.post(s, "p", "Saeko Kirigaya", "Saeko Kirigaya", "Thursday.", deliver_at=2)
    assert phone.unread(s, "p") == {}
    phone.advance(s, "p"); phone.advance(s, "p")
    assert phone.unread(s, "p") == {"Saeko Kirigaya": 1}


def test_unprompted_texts_are_rate_limited():
    s = _s()
    assert phone.may_text_first(s, "p")
    phone.mark_unprompted(s, "p")
    assert not phone.may_text_first(s, "p")
    for _ in range(4):
        phone.advance(s, "p")
    assert phone.may_text_first(s, "p")
