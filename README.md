# minicompressor

A tiny file compressor built from scratch in pure-stdlib Python, using the
same two-stage design as DEFLATE (the algorithm inside gzip/zip/PNG):

1. **LZSS** — replaces repeated byte sequences with back-references to
   earlier occurrences within a 32KB window.
2. **Huffman coding** — entropy-codes the resulting literals/matches so
   frequent symbols cost fewer bits.

No `zlib`, no third-party dependencies — both stages are implemented from
scratch. See [ARCHITECTURE.md](./ARCHITECTURE.md) for a full walkthrough of
how each module works.

## Install

Requires Python 3.10+.

```bash
cd minicompressor
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## CLI

```bash
.venv/bin/minicompress myfile.txt              # writes myfile.txt.mc, keeps the original
.venv/bin/minicompress -d myfile.txt.mc         # writes myfile.txt, keeps the .mc
.venv/bin/minicompress -o out.mc myfile.txt     # explicit output path
.venv/bin/minicompress -d -o out.txt myfile.txt.mc
```

Nothing is ever deleted — both compress and decompress always write a new
file alongside the input.

## Library

```python
from minicompressor import compress_bytes, decompress_bytes, compress_file, decompress_file

compressed = compress_bytes(b"hello hello hello")
assert decompress_bytes(compressed) == b"hello hello hello"

compress_file("myfile.txt")            # -> myfile.txt.mc
decompress_file("myfile.txt.mc")       # -> myfile.txt
```

## Tests

```bash
.venv/bin/pytest
```

## Notes

- Pure Python bit-level I/O means this is meant for learning/tinkering, not
  for compressing gigabyte-scale files quickly.
- Highly repetitive or text-like data compresses well (that's what LZSS +
  Huffman are good at); already-compressed data (zip, jpg, mp4, ...) won't
  shrink much, and may even grow slightly due to the header overhead.
