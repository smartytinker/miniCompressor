from minicompressor.bitio import BitReader, BitWriter


def test_write_and_read_bits_round_trip():
    writer = BitWriter()
    writer.write_bits(0b101, 3)
    writer.write_bits(0b1, 1)
    writer.write_bits(0b11001, 5)

    data = writer.getvalue()
    reader = BitReader(data, writer.total_bits())
    assert reader.read_bits(3) == 0b101
    assert reader.read_bits(1) == 0b1
    assert reader.read_bits(5) == 0b11001
    assert reader.has_more() is False


def test_write_code_matches_write_bits():
    writer = BitWriter()
    writer.write_code("1011")
    data = writer.getvalue()
    reader = BitReader(data, writer.total_bits())
    assert reader.read_bits(4) == 0b1011


def test_non_byte_aligned_length_pads_with_zero_bits():
    writer = BitWriter()
    writer.write_bits(1, 1)
    assert writer.total_bits() == 1
    data = writer.getvalue()
    assert len(data) == 1
    assert data[0] == 0b10000000


def test_many_small_writes_round_trip():
    bits = [1, 0, 1, 1, 0, 0, 1, 0, 1, 0, 1, 1, 1]
    writer = BitWriter()
    for b in bits:
        writer.write_bits(b, 1)
    data = writer.getvalue()
    reader = BitReader(data, writer.total_bits())
    read_back = [reader.read_bit() for _ in bits]
    assert read_back == bits


def test_read_past_end_raises():
    writer = BitWriter()
    writer.write_bits(1, 1)
    reader = BitReader(writer.getvalue(), writer.total_bits())
    reader.read_bit()
    try:
        reader.read_bit()
        assert False, "expected EOFError"
    except EOFError:
        pass
