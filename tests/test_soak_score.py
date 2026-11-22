import json

from tools.soak_score import score


def test_the_scorecard_counts_what_slipped_through(tmp_path):
    rows = [
        {"turn": 1, "action": "I wait.", "seconds": 10, "narration": "Rain hammers the tin awning above the noodle stall tonight. / Mama Sato: Sit down, child."},
        {"turn": 2, "action": "I wait more.", "seconds": 20, "narration": "Rain hammers the tin awning above the noodle stall tonight again. / Mama Sato: Sit down, child. / You nod. You agree to help her.",
         "notes": ["[sample line cut: x]", "[promise: Mama Sato: find Kenta]", "[referee: moved_to had no match in the scene, ignored]"]},
        {"turn": 3, "action": "I look.", "seconds": 30, "narration": "", "error": "Boom"},
        {"summary": {}},
    ]
    path = tmp_path / "s.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    s = score(path)
    assert s["turns"] == 3 and s["errors"] == 1 and s["empty_turns"] == 1 and s["median_seconds"] == 20
    assert s["repeated_8word_runs"] == 3  # "rain hammers ... tonight" is 10 words: three 8-word runs
    assert s["npc_lines"] == 2 and s["npc_distinct_openings"] == 0.5
    assert s["acted_for_player"] == 2  # "nod" and "agree" were not in the action
    assert (s["sample_lines_cut"], s["promises"], s["referee_ignored"]) == (1, 1, 1)


def test_memory_probes_read_the_end_state_and_say_none_for_older_soaks():
    from tools.soak_score import probes
    assert set(probes({}).values()) == {None}
    end = {"npc_memory": {"Wataru Ono": [{"text": "Rin said she already paid this week"}]}, "promises": [{"who": "Old Hara", "what": "bring him tea tomorrow"}], "journal": [],
           "people": {"Goro": {"weight": 2}}, "deeds": [{"knows": {"Goro": {"seen": True}, "Hara": {"seen": False}}}],
           "places": {"Ikebe Low": {"heat": 1, "warmth": 0, "marks": []}}, "events_used": {"comeback": 30}}
    assert set(probes(end).values()) == {True}
    assert probes({**end, "promises": []})["tea_promise_survives_undo"] is False
