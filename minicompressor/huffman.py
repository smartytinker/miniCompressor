"""Canonical Huffman coding: frequencies -> code lengths -> codes, and back.

Canonical codes are used so the code table can be serialized as just
(symbol, code length) pairs -- the decoder rebuilds the exact same codes
from those lengths alone, per RFC 1951's canonical-code algorithm.
"""

import heapq
import itertools
import struct


def build_code_lengths(freqs: dict) -> dict:
    """Build a Huffman tree over `{symbol: frequency}` and return `{symbol: code_length}`."""
    if not freqs:
        return {}
    if len(freqs) == 1:
        (symbol,) = freqs
        return {symbol: 1}

    counter = itertools.count()
    heap = [(freq, next(counter), symbol) for symbol, freq in freqs.items()]
    heapq.heapify(heap)

    while len(heap) > 1:
        freq1, _, node1 = heapq.heappop(heap)
        freq2, _, node2 = heapq.heappop(heap)
        heapq.heappush(heap, (freq1 + freq2, next(counter), (node1, node2)))

    _, _, root = heap[0]

    lengths = {}
    stack = [(root, 0)]
    while stack:
        node, depth = stack.pop()
        if isinstance(node, tuple):
            left, right = node
            stack.append((left, depth + 1))
            stack.append((right, depth + 1))
        else:
            lengths[node] = depth
    return lengths


def codes_from_lengths(lengths: dict) -> dict:
    """Assign canonical binary codes (as '0'/'1' strings) given each symbol's code length."""
    if not lengths:
        return {}

    max_len = max(lengths.values())
    bl_count = [0] * (max_len + 1)
    for length in lengths.values():
        bl_count[length] += 1

    code = 0
    next_code = [0] * (max_len + 1)
    for bits in range(1, max_len + 1):
        code = (code + bl_count[bits - 1]) << 1
        next_code[bits] = code

    codes = {}
    for symbol in sorted(lengths.keys()):
        length = lengths[symbol]
        codes[symbol] = format(next_code[length], f"0{length}b")
        next_code[length] += 1
    return codes


def make_decode_table(codes: dict) -> dict:
    """Invert a {symbol: code} mapping into {code: symbol} for decoding."""
    return {code: symbol for symbol, code in codes.items()}


def decode_symbol(reader, decode_table: dict):
    """Read bits one at a time from `reader` until they spell out a known code."""
    code = ""
    while True:
        code += str(reader.read_bit())
        symbol = decode_table.get(code)
        if symbol is not None:
            return symbol


def serialize_lengths(lengths: dict) -> bytes:
    """Encode {symbol: code_length} as a compact table: count, then (symbol, length) pairs."""
    items = sorted(lengths.items())
    out = bytearray(struct.pack(">H", len(items)))
    for symbol, length in items:
        out += struct.pack(">HB", symbol, length)
    return bytes(out)


def deserialize_lengths(data: bytes, offset: int):
    """Inverse of serialize_lengths. Returns (lengths, new_offset)."""
    (count,) = struct.unpack_from(">H", data, offset)
    offset += 2
    lengths = {}
    for _ in range(count):
        symbol, length = struct.unpack_from(">HB", data, offset)
        offset += 3
        lengths[symbol] = length
    return lengths, offset
