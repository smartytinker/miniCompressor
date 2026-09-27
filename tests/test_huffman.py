from minicompressor import huffman
from minicompressor.bitio import BitReader, BitWriter


def test_single_symbol_gets_one_bit_code():
    lengths = huffman.build_code_lengths({42: 5})
    assert lengths == {42: 1}
    codes = huffman.codes_from_lengths(lengths)
    assert codes == {42: "0"}


def test_more_frequent_symbol_gets_shorter_or_equal_code():
    freqs = {"a": 100, "b": 10, "c": 1, "d": 1}
    lengths = huffman.build_code_lengths(freqs)
    assert lengths["a"] <= lengths["b"] <= lengths["c"]
    assert lengths["a"] <= lengths["d"]


def test_codes_are_prefix_free():
    freqs = {i: (i + 1) for i in range(10)}
    lengths = huffman.build_code_lengths(freqs)
    codes = list(huffman.codes_from_lengths(lengths).values())
    for i, code_a in enumerate(codes):
        for code_b in codes[i + 1 :]:
            shorter, longer = sorted((code_a, code_b), key=len)
            assert not longer.startswith(shorter)


def test_serialize_deserialize_round_trip():
    lengths = {5: 2, 300: 3, 7: 2, 1: 1}
    data = huffman.serialize_lengths(lengths)
    restored, offset = huffman.deserialize_lengths(data, 0)
    assert restored == lengths
    assert offset == len(data)


def test_empty_lengths_round_trip():
    data = huffman.serialize_lengths({})
    restored, offset = huffman.deserialize_lengths(data, 0)
    assert restored == {}
    assert offset == len(data)


def test_encode_decode_round_trip_through_bitstream():
    freqs = {"x": 5, "y": 3, "z": 1, "w": 1}
    lengths = huffman.build_code_lengths(freqs)
    codes = huffman.codes_from_lengths(lengths)
    decode_table = huffman.make_decode_table(codes)

    symbols = ["x", "x", "y", "z", "w", "x", "y"]
    writer = BitWriter()
    for s in symbols:
        writer.write_code(codes[s])

    reader = BitReader(writer.getvalue(), writer.total_bits())
    decoded = [huffman.decode_symbol(reader, decode_table) for _ in symbols]
    assert decoded == symbols
