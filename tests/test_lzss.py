import os

from minicompressor import lzss


def _round_trip(data: bytes):
    tokens = lzss.compress(data)
    return lzss.decompress(tokens), tokens


def test_empty_input():
    result, tokens = _round_trip(b"")
    assert result == b""
    assert tokens == []


def test_single_byte():
    result, tokens = _round_trip(b"x")
    assert result == b"x"


def test_short_input_below_min_match_has_no_matches():
    result, tokens = _round_trip(b"ab")
    assert result == b"ab"
    assert all(isinstance(t, lzss.Literal) for t in tokens)


def test_repetitive_run_produces_a_match():
    data = b"a" * 100
    result, tokens = _round_trip(data)
    assert result == data
    assert any(isinstance(t, lzss.Match) for t in tokens)
    # Should compress to far fewer tokens than input bytes.
    assert len(tokens) < 10


def test_repeated_pattern_round_trips():
    data = b"abcabcabcabcabcabcabc"
    result, tokens = _round_trip(data)
    assert result == data
    assert any(isinstance(t, lzss.Match) for t in tokens)


def test_overlapping_match_distance_less_than_length():
    # "ab" then 20 more copies of "ab" -- a match with distance 2 and length > 2.
    data = b"ab" * 20
    result, tokens = _round_trip(data)
    assert result == data


def test_random_incompressible_data_round_trips():
    data = os.urandom(2000)
    result, tokens = _round_trip(data)
    assert result == data


def test_text_with_repetition_round_trips():
    data = (b"the quick brown fox jumps over the lazy dog. " * 20) + b"the end."
    result, tokens = _round_trip(data)
    assert result == data
    assert any(isinstance(t, lzss.Match) for t in tokens)


def test_data_larger_than_window_round_trips():
    data = os.urandom(40000)
    result, tokens = _round_trip(data)
    assert result == data
