# minicompressor internals — how it all works

This document walks through every file in `minicompressor/` and explains
what it does and why it's built that way. Read it top to bottom if you want
to understand the whole system; jump to a section if you just need one
piece.

## The mental model, in one paragraph

minicompressor is a two-stage pipeline, the same shape DEFLATE (the
algorithm inside gzip/zip/PNG) uses. First, **LZSS** turns the raw bytes into
a stream of tokens — literal bytes, or `(length, distance)` back-references
to earlier matching data — which is what captures repetition. Then
**Huffman coding** takes that token stream and packs it into as few bits as
possible, giving shorter codes to whatever symbols show up most often, which
is what captures skewed byte distributions (English text isn't a uniform
distribution over 256 byte values; neither is a token stream full of one
especially common match length). The two stages don't know anything about
each other's internals — LZSS only knows about bytes and back-references,
Huffman only knows about symbols and frequencies — and `container.py` is the
glue that defines how LZSS's tokens become Huffman's symbol alphabet, and how
both get packed into one file on disk.

## Directory map

```
minicompressor/
  minicompressor/
    bitio.py         # BitWriter/BitReader — pack individual bits into bytes
    huffman.py         # frequencies -> canonical Huffman codes, and back
    lzss.py              # raw bytes <-> tokens (literals + back-references)
    container.py          # tokens <-> symbols, the .mc file format, compress_bytes/decompress_bytes
    cli.py                  # `minicompress` command-line tool
    __init__.py              # public exports
    __main__.py               # lets you run `python -m minicompressor`
  tests/
    test_bitio.py        # bit-level read/write round trips
    test_huffman.py       # code correctness, prefix-freedom, serialization
    test_lzss.py            # token round trips, overlapping matches, large inputs
    test_container.py        # full file-format round trips, compression sanity checks
    test_cli.py                # the CLI's compress/decompress commands end to end
```

The files build on each other in this order: **bitio.py** and **lzss.py**
have no dependencies on the rest of the package; **huffman.py** depends only
on `bitio.py`'s reader for decoding; **container.py** imports both `huffman`
and `lzss` and is where they actually meet; **cli.py** imports
`container.py`. That's also the order that makes sense to read them in, so
that's the order below.

---

## `bitio.py` — packing bits into bytes

Huffman codes are variable-length strings of bits (`"0"`, `"110"`,
`"10111"`, ...) that almost never line up on byte boundaries, so before
anything can be written to a file, those bits need to be packed together.
That's the entirety of what this file does — it has no idea what a Huffman
code or an LZSS token is.

**`BitWriter`** accumulates bits into a `bytearray`. `write_bits(value,
nbits)` walks the requested bits of `value` from most-significant to
least-significant, and for each one: shifts it into a one-byte accumulator
(`self._current`), and once that accumulator has collected a full 8 bits,
appends it to the output and resets. `write_code(code)` is a convenience
wrapper for the common case where a Huffman code is already a string like
`"1011"` — it just calls `write_bits` once per character. `getvalue()`
returns everything written so far; if the last byte isn't full, it left-pads
that byte with zero bits (`self._current << (8 - self._nbits)`) rather than
leaving it incomplete — those trailing zero bits are why the file format
separately records the *exact* number of meaningful bits (see
`container.py`), so the reader knows not to try to decode them as real data.

**`BitReader`** is the mirror image: constructed with the raw bytes *and* the
exact bit count that's meaningful (`total_bits`), so it knows exactly where
to stop even though the underlying byte array is padded. `read_bit()` pulls
one bit out of `self._data[self._pos // 8]` at bit offset `7 - (self._pos %
8)` (MSB-first, matching how `BitWriter` packed them), and raises `EOFError`
if asked to read past `total_bits` — a real bug (misaligned encoder/decoder)
should crash loudly here, not silently return garbage. `read_bits(nbits)`
just calls `read_bit()` in a loop and accumulates the result.

## `huffman.py` — frequencies in, canonical codes out

This module's job: given how often each symbol occurs, produce a
prefix-free binary code for each one — short codes for frequent symbols,
long codes for rare ones — such that no code is a prefix of another (so a
decoder reading bit-by-bit never has ambiguity about when one code ends and
the next begins).

**`build_code_lengths(freqs)`** builds the actual Huffman tree, using the
standard algorithm: repeatedly pull the two least-frequent nodes off a
min-heap and merge them into a new internal node whose frequency is their
sum, until one node (the root) is left. `heapq` needs every item on the heap
to be comparable, but tree nodes are either a bare symbol (an int, or
whatever hashable value the caller used) or a tuple of two child nodes once
merged — comparing those directly would eventually try to compare a tuple of
nodes against a plain symbol and blow up. The fix is `itertools.count()`
as a tie-breaker: every heap entry is `(frequency, unique_counter, node)`,
and since the counter is always unique, Python's tuple comparison never has
to look past it to compare `node` values at all. Once the tree is built, a
plain iterative depth-first walk (using an explicit stack, not recursion)
computes each leaf's depth — a leaf's depth *is* its code length, since a
Huffman tree's shape directly encodes "how many bits to reach this symbol
from the root." A single-symbol alphabet is special-cased to a 1-bit code,
since the merge loop needs at least two nodes to do anything, and a 0-bit
code isn't representable in `BitWriter`/`BitReader` anyway (there's no way
to "read zero bits" and learn anything).

**`codes_from_lengths(lengths)`** is a separate step from building the tree:
given just the code *lengths* (not the tree shape), it assigns actual binary
codes using the canonical Huffman algorithm — symbols are sorted by
`(code length, symbol value)`, and codes are handed out in that order,
incrementing a counter and left-shifting whenever the code length increases.
The payoff for doing it this way, instead of just reading codes directly off
the tree built above, is that **the codes are now a pure function of the
lengths alone** — a decoder that's told "symbol 5 has code length 3, symbol
9 has code length 2, ..." can reconstruct the *exact same* codes without
ever seeing the tree. That's what makes `serialize_lengths` /
`deserialize_lengths` able to store just `(symbol, length)` pairs in the
file instead of a full tree structure.

**`make_decode_table(codes)`** just inverts `{symbol: code}` into `{code:
symbol}`. **`decode_symbol(reader, decode_table)`** reads one bit at a time,
appending each to a growing string, until that string matches some key in
the decode table — since the code is prefix-free, the *first* match found
this way is guaranteed to be the intended symbol, never a false partial
match. This is simple rather than fast (it's an `O(code length)` dict lookup
per bit rather than a proper trie or table-driven decode), which is the
right trade for a "mini" implementation.

**`serialize_lengths`/`deserialize_lengths`** turn a `{symbol: length}` dict
into bytes and back, using `struct`: a 2-byte count, then for each entry a
2-byte symbol and a 1-byte length. Symbols are sorted before serializing
purely so the output is deterministic (useful for tests), not because
deserialization requires any particular order.

## `lzss.py` — finding repetition

This is the "replace repeated data with a pointer to where it happened
before" stage. Its two data types are simple: `Literal(byte)` for a single
byte that couldn't be matched, and `Match(length, distance)` for "copy
`length` bytes from `distance` bytes back in the output."

**The parameters** (`WINDOW_SIZE = 32768`, `MIN_MATCH = 3`, `MAX_MATCH =
258`) are the same bounds DEFLATE itself uses — a match has to be at least 3
bytes to be worth encoding as a back-reference instead of 3 literals, and is
capped at 258 bytes so the length fits compactly into `container.py`'s
symbol alphabet (see below). `WINDOW_SIZE` bounds how far back a match can
point, which bounds how much of the input needs to stay "in view" at once.

**Why a hash chain, not brute force.** The naive way to find the best match
at position `i` is to compare against every earlier position within the
window — that's `O(window size)` work per byte, `O(n * window)` overall,
which gets slow fast. Instead, `head` maps `hash(3 bytes) -> most recent
position with that hash`, and `prev` is a parallel array where `prev[pos]`
points to the *previous* position that had the same hash (a linked list of
same-hash positions, threaded through the array). To find matches at
position `i`: hash the 3 bytes there, look up the most recent position with
that hash, check how long the match actually runs (`_match_length`), then
follow `prev` to the position before that, and repeat — capped at
`MAX_CHAIN` (32) steps so a pathological input (like a file that's all the
same byte) can't force a huge linear scan at every position. This is exactly
the technique zlib uses internally.

**`_match_length(data, a, b, n)`** compares bytes starting at earlier
position `a` and current position `b`, byte by byte, until they differ or
`MAX_MATCH`/end-of-data is hit. Because `a < b`, once a match candidate's
length grows past `b - a`, the comparison starts reading bytes *within* the
match itself (`data[a + length]` where `a + length >= b`) — that's fine
here, since at compression time the *entire* input is already sitting in
memory; there's no "we haven't produced that output yet" problem the way
there is at decompression time.

**`compress(data)`** walks through the input once. At each position, it
either found a match of at least `MIN_MATCH` — in which case it emits one
`Match` token, inserts hash-chain entries for every position the match
covered (so future searches can also match into the middle of it), and jumps
the position forward by the whole match length — or it didn't, in which case
it emits a `Literal`, inserts one hash entry, and advances by one byte.

**`decompress(tokens)`** replays the tokens: append literal bytes directly;
for a match, copy `length` bytes **one at a time** from `distance` bytes
back in the output built *so far*. This has to be byte-at-a-time, not a bulk
slice copy, because `distance` can be *smaller* than `length` — e.g. a run
of `"aaaaaaaa"` gets encoded as one literal `'a'` plus a `Match(length=7,
distance=1)`, and correctly expanding that means each newly-copied byte
becomes readable as the source for the *next* copy in the same match. A bulk
`output[-distance:]` slice, taken once upfront, would only see the output
that existed *before* the match started and get it wrong.

## `container.py` — where LZSS and Huffman meet, and the file format

**The symbol alphabet.** Huffman codes symbols, not bytes-or-tuples, so
LZSS's two kinds of tokens need to be flattened into one number line:
- `0–255`: a literal byte, symbol == the byte value.
- `256`: an explicit end-of-stream marker, so the decoder knows when to stop
  (rather than needing a separately-stored token count).
- `257–512`: a match, encoding its length (`3–258`) as `257 + (length - 3)`
  — this is why `MAX_MATCH` is capped at 258: it's exactly 256 possible
  values, fitting the alphabet neatly.

Match *distances* don't fit that same alphabet (they range up to 32768, and
mixing them into the same tree as literals/lengths would dilute the
frequency statistics for both), so they get their own, separate Huffman
tree. The two trees share a single bitstream by *position*, exactly like
DEFLATE: the decoder always decodes one literal/length symbol first; only if
that symbol turns out to represent a match does it immediately decode one
more symbol, this time from the distance tree, right after it. There's never
any ambiguity about which tree to read from next, because it's fully
determined by what was just decoded.

**`compress_bytes(data)`**: runs `lzss.compress`, then walks the resulting
tokens twice. First pass: build frequency tables — one for literal/length
symbols (seeded with `{END_SYMBOL: 1}` so the end marker always has a code,
even for empty input with no other tokens at all) and one for distances
(built only from `Match` tokens, so it stays empty if the input never
repeats). Those frequencies go into `huffman.build_code_lengths` /
`codes_from_lengths` to get two independent code tables. Second pass:
actually write the bitstream — one literal/length code per token, plus a
distance code immediately after for match tokens, plus one final
end-of-stream code. Finally, everything is assembled into the file: magic
bytes, original length (used as a sanity check on decompress, not strictly
required for correctness since the end marker already terminates decoding),
both serialized code-length tables, the bitstream's exact bit count, and the
packed bitstream itself.

**`decompress_bytes(data)`** reverses every step: check the magic bytes,
read the original length, deserialize both code-length tables and rebuild
their canonical codes (via the exact same `codes_from_lengths` used to
encode — this only works because canonical codes are a pure function of
lengths, as described in `huffman.py` above), then decode symbols one at a
time until hitting `END_SYMBOL`. Any symbol `>= 257` triggers an immediate
extra `decode_symbol` call against the distance table to get that match's
distance. The resulting token list is handed to `lzss.decompress`, and the
final byte count is checked against the length stored in the header as a
basic corruption check.

**`compress_file`/`decompress_file`** are the file-system-facing wrappers
the CLI uses: `compress_file` defaults the output path to the input's name
with `.mc` appended (`myfile.txt` -> `myfile.txt.mc`); `decompress_file`
defaults to stripping a trailing `.mc` (`Path.stem` on `myfile.txt.mc` is
exactly `myfile.txt`, since `.mc` is the only suffix `Path` sees) and raises
a clear error if the input doesn't end in `.mc` and no explicit output was
given — there'd be no sane default name to fall back to.

## `cli.py` — the command-line tool

Unlike `minidb`'s CLI (which is a REPL that needs to parse a whole small
grammar per line), this one is a single-shot command, so it's built on
`argparse` — the standard-library tool for exactly this shape of interface
— rather than a hand-rolled parser: `minicompress <file>` to compress,
`-d`/`--decompress` to go the other way, `-o`/`--output` for an explicit
output path. `main(argv=None)` takes an optional argument list (defaulting
to `sys.argv[1:]` inside `argparse` itself) purely so `tests/test_cli.py`
can call `main([...])` directly instead of spawning a subprocess. After
compressing or decompressing, it prints both file sizes and, for
compression, the ratio — mostly so running the tool gives you an immediate
sanity check that it actually did something reasonable.

## `__init__.py` and `__main__.py`

`__init__.py` re-exports `compress_bytes`, `decompress_bytes`,
`compress_file`, and `decompress_file` at the top of the package, so
`from minicompressor import compress_file` works without reaching into
`minicompressor.container`. `__main__.py` is what makes `python -m
minicompressor` work — Python looks for exactly this file when a package is
run with `-m`, and it just calls `cli.main()`.

## Tracing one full round trip

To see every layer at once, here's what happens for
`minicompress mydata.txt` where `mydata.txt` contains `"ababab"`:

1. `cli.main` parses the arguments, sees no `-d`, and calls
   `compress_file("mydata.txt")`.
2. `compress_file` reads the 6 bytes `b"ababab"` and calls
   `compress_bytes` on them.
3. `lzss.compress` walks the bytes: at position 0 there's no match yet (the
   hash chain is empty), so it emits `Literal(b'a')`, then `Literal(b'b')`.
   At position 2, the hash chain now has an entry for the 3-byte prefix
   starting at position 0 (`"aba"`), which matches the 3-byte prefix at
   position 2 too — the match extends the full remaining length, so it
   emits `Match(length=4, distance=2)` and stops. Token stream:
   `[Literal('a'), Literal('b'), Match(4, 2)]`.
4. `compress_bytes` converts those into symbols: `97`, `98` (ASCII for
   `'a'`/`'b'`), and `257 + (4 - 3) = 258` for the match, plus the implicit
   `256` end marker. It tallies frequencies, builds a literal/length
   Huffman tree over `{97: 1, 98: 1, 258: 1, 256: 1}` and a distance tree
   over `{2: 1}`, then writes: the code for `97`, the code for `98`, the
   code for `258` immediately followed by the code for distance `2`, then
   the code for `256`.
5. The header (magic, original length `6`, both serialized code tables, bit
   count) is prepended, and the whole thing is written to `mydata.txt.mc`.
6. Running `minicompress -d mydata.txt.mc` reverses every step: rebuild both
   Huffman trees from the stored lengths, decode symbols `97`, `98`, then
   `258` (recognized as `>= 257`, so immediately decode one more symbol from
   the distance tree, getting `2`) giving back `Match(length=4,
   distance=2)`, then `256` (stop). `lzss.decompress` replays
   `[Literal('a'), Literal('b'), Match(4, 2)]`: output starts `"ab"`, then
   the match copies 4 bytes starting 2 back from the current end —
   byte-by-byte, so it reads back `"a", "b", "a", "b"` as the output grows —
   landing on `"ababab"`, matching the original exactly.

## Why these design choices

- **LZSS before Huffman, not the other way around** — this is the order
  DEFLATE uses, and it's the order that makes sense: LZSS removes
  *structural* repetition (the same substring occurring more than once),
  which Huffman coding can't do (it only ever looks at one symbol at a
  time); Huffman then removes *statistical* skew (some symbols being more
  common than others) from whatever LZSS leaves behind.
- **Canonical Huffman codes over "just store the tree"** — storing a tree
  directly (or the codes themselves) would cost far more header bytes than
  storing one length byte per symbol, especially for the distance alphabet
  which can have symbols up to 32768.
- **Hash-chain match finding over brute force** — without it, LZSS
  compression time would grow with `window size × input length`, which
  would make compressing anything beyond a few KB noticeably slow.
- **A hard `MAX_CHAIN` cap** — without it, a pathological input (long runs
  of the same byte or repeating short pattern) could make every single
  position's search walk a huge hash chain, turning a mostly-linear
  algorithm quadratic on exactly the inputs it's supposed to handle best.
- **An explicit end-of-stream symbol over a stored token count** — it means
  the decoder doesn't need to know in advance how many tokens to expect; it
  just decodes until it sees `256`, which is simpler and mirrors how
  DEFLATE itself terminates a block.
