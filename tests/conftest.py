import pytest


@pytest.fixture(autouse=True)
def _ratings_file(tmp_path, monkeypatch):
    """Ratings are shared play data (design-data/turn-ratings.jsonl); tests never read or write the real file."""
    monkeypatch.setenv("NIGHTWIRE_RATINGS", str(tmp_path / "turn-ratings.jsonl"))
