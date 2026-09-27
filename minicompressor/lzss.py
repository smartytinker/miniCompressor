"""LZSS: turn raw bytes into a stream of literals and (length, distance) back-references.

Matches are found with a hash-chain over 3-byte prefixes (the same technique
zlib uses), which keeps compression close to linear time instead of the
O(n * window) cost of a brute-force search.
"""

from collections import namedtuple

WINDOW_SIZE = 32768
MIN_MATCH = 3
MAX_MATCH = 258
MAX_CHAIN = 32
_HASH_SIZE = 1 << 15

Literal = namedtuple("Literal", ["byte"])
Match = namedtuple("Match", ["length", "distance"])


def _hash3(data: bytes, i: int) -> int:
    return ((data[i] << 16) | (data[i + 1] << 8) | data[i + 2]) % _HASH_SIZE


def _match_length(data: bytes, a: int, b: int, n: int) -> int:
    """Length of the common run starting at `a` and `b` (a < b), capped at MAX_MATCH."""
    max_len = min(MAX_MATCH, n - b)
    length = 0
    while length < max_len and data[a + length] == data[b + length]:
        length += 1
    return length


def compress(data: bytes):
    n = len(data)
    tokens = []
    head: dict = {}
    prev = [-1] * n

    i = 0
    while i < n:
        best_len = 0
        best_dist = 0

        if i + 3 <= n:
            h = _hash3(data, i)
            candidate = head.get(h, -1)
            window_start = max(0, i - WINDOW_SIZE)
            chain = 0
            while candidate >= window_start and chain < MAX_CHAIN:
                match_len = _match_length(data, candidate, i, n)
                if match_len > best_len:
                    best_len = match_len
                    best_dist = i - candidate
                    if best_len >= MAX_MATCH:
                        break
                candidate = prev[candidate]
                chain += 1

        if best_len >= MIN_MATCH:
            tokens.append(Match(best_len, best_dist))
            end = i + best_len
            while i < end and i + 3 <= n:
                h = _hash3(data, i)
                prev[i] = head.get(h, -1)
                head[h] = i
                i += 1
            i = end
        else:
            tokens.append(Literal(data[i]))
            if i + 3 <= n:
                h = _hash3(data, i)
                prev[i] = head.get(h, -1)
                head[h] = i
            i += 1

    return tokens


def decompress(tokens) -> bytes:
    out = bytearray()
    for token in tokens:
        if isinstance(token, Literal):
            out.append(token.byte)
        else:
            start = len(out) - token.distance
            for k in range(token.length):
                out.append(out[start + k])
    return bytes(out)
