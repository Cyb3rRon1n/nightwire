from narrator.designs import Design
from tools import design_check as dc


def test_missing_forbidden_and_unchecked():
    panels = [{"red hair": 0.9, "cigarette": 0.7, "purple eyes": 0.1, "holding": 0.0}, {"red hair": 0.1, "cigarette": 0.0, "purple eyes": 0.1, "holding": 0.0}]
    got = dc.judge_tags(["red hair", "purple eyes", "chrome jaw"], ["cigarette", "holding", "made up"], panels)
    assert got == {"missing": {"red hair": 1, "purple eyes": 2}, "forbidden": {"cigarette": 1}, "unchecked": ["chrome jaw"]}


def test_canon_details_are_not_forbidden_but_carried_items_are():
    d = Design(name="K", kind="character", source="x", tags="fang, cigarette, visor", required=["visor"], held=["cigarette"], negative="child")
    terms = dc.forbidden_terms(d)
    assert "fangs" not in terms and "visor" not in terms and "cigarette" in terms and "child" in terms


def test_flags_use_thresholds():
    entry = {"forbidden": {"cigarette": 2}, "missing": {"red hair": 3, "scar": 1},
             "worst_panel_pair": {"a": "Smile", "b": "Sad", "difference": 0.5}, "nearest": {"slug": "rin", "difference": 0.05}}
    flags = dc.flags_for(entry)
    assert len(flags) == 4 and "looks like rin" in flags[3]
    assert len(dc.flags_for({"forbidden": {}, "missing": {}, "worst_panel_pair": {"a": "a", "b": "b", "difference": 0.1}, "nearest": {"slug": "r", "difference": 0.9}})) == 0
