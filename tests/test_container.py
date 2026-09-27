import os

from minicompressor.container import compress_bytes, decompress_bytes


def test_empty_round_trip():
    compressed = compress_bytes(b"")
    assert decompress_bytes(compressed) == b""


def test_single_byte_round_trip():
    compressed = compress_bytes(b"x")
    assert decompress_bytes(compressed) == b"x"


def test_short_text_round_trip():
    data = b"hello, world!"
    compressed = compress_bytes(data)
    assert decompress_bytes(compressed) == data


def test_highly_repetitive_data_shrinks():
    data = b"abcdefgh" * 5000
    compressed = compress_bytes(data)
    assert decompress_bytes(compressed) == data
    assert len(compressed) < len(data) / 4


def test_random_incompressible_data_round_trips():
    data = os.urandom(5000)
    compressed = compress_bytes(data)
    assert decompress_bytes(compressed) == data


def test_text_round_trips_and_shrinks():
    paragraph = (
        b"The quick brown fox jumps over the lazy dog. " * 50
        + b"Pack my box with five dozen liquor jugs. " * 50
    )
    compressed = compress_bytes(paragraph)
    assert decompress_bytes(compressed) == paragraph
    assert len(compressed) < len(paragraph)


def test_bad_magic_raises():
    try:
        decompress_bytes(b"NOTMAGIC" + b"\x00" * 20)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_data_spanning_multiple_windows_round_trips():
    data = os.urandom(100000)
    compressed = compress_bytes(data)
    assert decompress_bytes(compressed) == data
