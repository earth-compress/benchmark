from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from conftest import write_corpus

from earthcompress import build
from earthcompress.corpus import load_samples


def test_the_exactness_test_of_section_one():
    codes = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.uint16)
    published = (codes * np.array([[0.25], [0.5]]) + np.array([[10.0], [-1.0]])).astype(
        np.float32
    )
    assert build.exact(codes, [0.25, 0.5], [10.0, -1.0], published)
    assert not build.exact(codes, [0.25, 0.5], [10.0, -1.5], published)


def test_a_float32_scale_reproduces_float32_products():
    counts = np.arange(5000, dtype=np.uint16)
    published = counts.astype(np.float32) * np.float32(0.01)
    assert not build.exact(counts, 0.01, 0.0, published)
    assert build.exact(counts, float(np.float32(0.01)), 0.0, published)


def test_cast_refuses_a_change_of_value():
    assert build.cast(np.array([1, 255], dtype=np.int32), "uint8").dtype == np.uint8
    with pytest.raises(ValueError):
        build.cast(np.array([-1, 5], dtype=np.int32), "uint8")


def test_a_transform_round_trips():
    text = build.transform_text(384420.0, 10.0, 3952180.0, -10.0)
    assert build.parse_transform(text) == (384420.0, 10.0, 0.0, 3952180.0, 0.0, -10.0)


def test_a_rebuild_must_match_the_manifest_digest(tmp_path: Path):
    corpus = write_corpus(tmp_path / "c", {"c-00": np.arange(8, dtype=np.uint16)})
    row = build.read_manifest(corpus)[0]
    build.save(corpus, dict(row), np.arange(8, dtype=np.uint16))
    with pytest.raises(ValueError, match="input_sha256"):
        build.save(corpus, dict(row), np.arange(1, 9, dtype=np.uint16))


def test_written_corpora_load_back(tmp_path: Path):
    data = np.arange(24, dtype=np.int8).reshape(2, 3, 4)
    corpus = write_corpus(tmp_path / "c", {"c-00": data}, nodata="-128")
    sample = load_samples(corpus)[0]
    assert np.array_equal(sample.data, data) and sample.sentinel == -128.0
