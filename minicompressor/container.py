"""Ties LZSS and Huffman together into the on-disk .mc format.

Symbol alphabet for the literal/length tree (mirrors DEFLATE's approach):
  0-255   literal byte values
  256     end-of-stream marker
  257-512 match length 3-258, as (symbol - 257 + MIN_MATCH)

Match distances are coded in a second, separate Huffman tree. The two trees
share one bitstream: whenever a length symbol is decoded, the very next
code in the stream is a distance code for that same match.

File layout:
  magic (4 bytes) | original length (8 bytes) |
  literal/length code-length table | distance code-length table |
  bitstream length in bits (4 bytes) | packed bitstream
"""

import struct
from pathlib import Path

from . import huffman, lzss
from .bitio import BitReader, BitWriter

MAGIC = b"MNC1"
END_SYMBOL = 256
LENGTH_BASE = 257


def _token_to_litlen_symbol(token) -> int:
    if isinstance(token, lzss.Literal):
        return token.byte
    return LENGTH_BASE + (token.length - lzss.MIN_MATCH)


def compress_bytes(data: bytes) -> bytes:
    tokens = lzss.compress(data)

    litlen_freqs: dict = {END_SYMBOL: 1}
    dist_freqs: dict = {}
    for token in tokens:
        symbol = _token_to_litlen_symbol(token)
        litlen_freqs[symbol] = litlen_freqs.get(symbol, 0) + 1
        if isinstance(token, lzss.Match):
            dist_freqs[token.distance] = dist_freqs.get(token.distance, 0) + 1

    litlen_lengths = huffman.build_code_lengths(litlen_freqs)
    litlen_codes = huffman.codes_from_lengths(litlen_lengths)
    dist_lengths = huffman.build_code_lengths(dist_freqs)
    dist_codes = huffman.codes_from_lengths(dist_lengths)

    writer = BitWriter()
    for token in tokens:
        writer.write_code(litlen_codes[_token_to_litlen_symbol(token)])
        if isinstance(token, lzss.Match):
            writer.write_code(dist_codes[token.distance])
    writer.write_code(litlen_codes[END_SYMBOL])

    header = bytearray()
    header += MAGIC
    header += struct.pack(">Q", len(data))
    header += huffman.serialize_lengths(litlen_lengths)
    header += huffman.serialize_lengths(dist_lengths)
    header += struct.pack(">I", writer.total_bits())

    return bytes(header) + writer.getvalue()


def decompress_bytes(data: bytes) -> bytes:
    if data[:4] != MAGIC:
        raise ValueError("not a minicompressor (.mc) file: bad magic bytes")

    offset = 4
    (original_length,) = struct.unpack_from(">Q", data, offset)
    offset += 8

    litlen_lengths, offset = huffman.deserialize_lengths(data, offset)
    dist_lengths, offset = huffman.deserialize_lengths(data, offset)
    (total_bits,) = struct.unpack_from(">I", data, offset)
    offset += 4

    litlen_decode = huffman.make_decode_table(huffman.codes_from_lengths(litlen_lengths))
    dist_decode = huffman.make_decode_table(huffman.codes_from_lengths(dist_lengths))

    reader = BitReader(data[offset:], total_bits)
    tokens = []
    while True:
        symbol = huffman.decode_symbol(reader, litlen_decode)
        if symbol == END_SYMBOL:
            break
        if symbol < 256:
            tokens.append(lzss.Literal(symbol))
        else:
            length = symbol - LENGTH_BASE + lzss.MIN_MATCH
            distance = huffman.decode_symbol(reader, dist_decode)
            tokens.append(lzss.Match(length, distance))

    result = lzss.decompress(tokens)
    if len(result) != original_length:
        raise ValueError("corrupt .mc file: decompressed length does not match header")
    return result


def compress_file(input_path, output_path=None) -> Path:
    input_path = Path(input_path)
    output_path = Path(output_path) if output_path is not None else input_path.parent / (input_path.name + ".mc")
    output_path.write_bytes(compress_bytes(input_path.read_bytes()))
    return output_path


def decompress_file(input_path, output_path=None) -> Path:
    input_path = Path(input_path)
    if output_path is not None:
        output_path = Path(output_path)
    else:
        if input_path.suffix != ".mc":
            raise ValueError("cannot infer output filename for a file not ending in .mc; pass an explicit output path")
        output_path = input_path.parent / input_path.stem
    output_path.write_bytes(decompress_bytes(input_path.read_bytes()))
    return output_path
