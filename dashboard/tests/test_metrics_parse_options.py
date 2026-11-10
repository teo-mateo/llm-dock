import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import metrics_catalogue
from flag_metadata import ENGINE_IMAGES
from metrics_catalogue import CURATED_METRICS, PARSE_OPTIONS, ParseOptions
from routes.metrics import _parse_metrics

FAKE = "fake"
TEXT = """# TYPE fake:tokens counter
fake:tokens_total{position="0"} 5
fake:tokens_total{position="1"} 7
fake:tokens_created{position="0"} 1.7e9
# TYPE fake:other counter
fake:other_total{role="a"} 3
fake:other_created{role="a"} 1.7e9
"""


@pytest.fixture
def fake_engine(monkeypatch):
    monkeypatch.setitem(CURATED_METRICS, FAKE, {"fake:tokens_total", "fake:other_total"})
    return FAKE


def _parse(engine):
    return _parse_metrics(TEXT, engine)


def test_an_engine_without_options_keys_every_sample_by_its_labels(fake_engine):
    parsed = _parse(fake_engine)

    assert parsed["fake:tokens_total"] == {"position=0": 5.0, "position=1": 7.0}
    assert parsed["fake:other_total"] == {"role=a": 3.0}


def test_a_position_family_option_keys_that_family_by_position(fake_engine, monkeypatch):
    monkeypatch.setitem(PARSE_OPTIONS, fake_engine, ParseOptions(position_family="fake:tokens_total"))

    parsed = _parse(fake_engine)

    assert parsed["fake:tokens_total"] == {"position_0": 5.0, "position_1": 7.0}
    assert parsed["fake:other_total"] == {"role=a": 3.0}


def test_the_drop_created_option_is_what_removes_created_samples(fake_engine, monkeypatch):
    without = _parse(fake_engine)
    monkeypatch.setitem(PARSE_OPTIONS, fake_engine, ParseOptions(drop_created_samples=True))
    dropped = _parse(fake_engine)

    assert dropped["fake:other_total"] == {"role=a": 3.0}
    assert set(without) == set(dropped)


def test_the_recorded_options_are_the_ones_the_parser_used_to_hard_code():
    assert PARSE_OPTIONS == {
        "vllm": ParseOptions(position_family="vllm:spec_decode_num_accepted_tokens_per_pos_total"),
        "sglang": ParseOptions(drop_created_samples=True),
    }


def test_options_only_name_curated_engines_and_families():
    assert set(PARSE_OPTIONS) <= set(CURATED_METRICS)
    for engine, options in PARSE_OPTIONS.items():
        if options.position_family:
            assert options.position_family in CURATED_METRICS[engine]


def test_the_metrics_route_names_no_engine():
    source = (Path(__file__).resolve().parent.parent / "routes" / "metrics.py").read_text()
    names = "|".join(map(re.escape, ENGINE_IMAGES))

    assert not re.findall(r"""(['"`])(%s)\1""" % names, source)
    assert metrics_catalogue.PARSE_OPTIONS is PARSE_OPTIONS
