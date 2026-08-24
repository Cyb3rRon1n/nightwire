from engine.session import Session
from narrator.tts_backend import VoiceOption
from narrator.voice_assignment import assign_voice

_BANK = [
    VoiceOption(id="af_heart", gender="female"),
    VoiceOption(id="af_bella", gender="female"),
    VoiceOption(id="am_adam", gender="male"),
    VoiceOption(id="am_michael", gender="male"),
]


def test_assign_voice_picks_the_first_matching_gender_for_a_new_speaker():
    session = Session(session_id="s1")

    voice = assign_voice(session, "Jax", "male", _BANK)

    assert voice == "am_adam"
    assert session.speaker_voices["jax"] == "am_adam"


def test_assign_voice_reuses_the_stored_voice_for_a_returning_speaker_ignoring_gender():
    session = Session(session_id="s1")
    session.speaker_voices["jax"] = "am_michael"

    voice = assign_voice(session, "Jax", "female", _BANK)

    assert voice == "am_michael"


def test_assign_voice_falls_back_to_the_full_bank_when_gender_is_none():
    session = Session(session_id="s1")

    voice = assign_voice(session, "narrator", None, _BANK)

    assert voice == "af_heart"


def test_assign_voice_gives_two_new_speakers_of_the_same_gender_different_voices():
    session = Session(session_id="s1")

    first = assign_voice(session, "Jax", "male", _BANK)
    second = assign_voice(session, "Chrome-9", "male", _BANK)

    assert first == "am_adam"
    assert second == "am_michael"
    assert first != second


def test_assign_voice_reuses_a_matching_voice_once_the_matching_pool_is_exhausted():
    session = Session(session_id="s1")
    assign_voice(session, "Jax", "male", _BANK)
    assign_voice(session, "Chrome-9", "male", _BANK)

    third = assign_voice(session, "Rook", "male", _BANK)

    assert third == "am_adam"  # both male voices already taken - reuse the first match


def test_assign_voice_falls_back_to_the_full_bank_when_no_voice_declares_that_gender():
    session = Session(session_id="s1")
    ungendered_bank = [VoiceOption(id="alloy"), VoiceOption(id="nova")]

    voice = assign_voice(session, "narrator", "male", ungendered_bank)

    assert voice == "alloy"


def test_assign_voice_treats_case_and_whitespace_variants_as_the_same_speaker():
    session = Session(session_id="s1")
    first = assign_voice(session, "Rico", "male", _BANK)

    second = assign_voice(session, " rico ", "female", _BANK)

    assert second == first
    assert len(session.speaker_voices) == 1
