"""Deterministic repairs of a model answer that would otherwise stop the build (finals: no manual step)."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from builder.policy import extract, schema  # noqa: E402

EN = {"outcomes": ["promise", "paid", "transferred", "no_promise", "not_verified", "not_reached"]}


def test_missing_situations_borrow_the_nearest_mapping():
    outcomes = {"promise": ["promise", None], "refused": ["no_promise", "refused"], "unclear": ["not_reached", "unclear"],
                "transfer_human": ["transferred", "human"], "id_failed": ["not_verified", "failed"]}
    problems = {}
    extract.fill_outcomes(outcomes, EN, problems)
    assert set(outcomes) == set(schema.SITUATIONS)
    assert outcomes["deceased"] == ["not_reached", "unclear"]
    assert outcomes["transfer_support"] == ["transferred", "human"]
    assert outcomes["id_declined"] == ["not_verified", "failed"]
    assert problems["outcomes"]


def test_band_gaps_are_closed():
    bands = [{"name": "B", "min": 11, "max": 60}, {"name": "A", "min": 1, "max": 9}]
    problems = {}
    out = extract.contiguous_bands(bands, problems)
    assert [(b["name"], b["min"], b["max"]) for b in out] == [("A", 1, 10), ("B", 11, 60)]
    assert problems["bands"]
