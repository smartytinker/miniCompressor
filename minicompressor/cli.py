"""Command-line interface for minicompressor.

  minicompress <file>                 # writes <file>.mc, keeps the original
  minicompress -d <file.mc>            # writes <file>, keeps the .mc
  minicompress -o <out> <file>          # explicit output path (works with -d too)
"""

import argparse
import sys
from pathlib import Path

from .container import compress_file, decompress_file


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="minicompress", description="A mini LZSS+Huffman file compressor.")
    parser.add_argument("file", help="file to compress, or to decompress with -d")
    parser.add_argument("-d", "--decompress", action="store_true", help="decompress instead of compress")
    parser.add_argument("-o", "--output", help="explicit output path")
    args = parser.parse_args(argv)

    input_path = Path(args.file)
    if not input_path.is_file():
        print(f"error: no such file: {input_path}", file=sys.stderr)
        return 1

    try:
        if args.decompress:
            output_path = decompress_file(input_path, args.output)
        else:
            output_path = compress_file(input_path, args.output)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    in_size = input_path.stat().st_size
    out_size = output_path.stat().st_size
    verb = "Decompressed" if args.decompress else "Compressed"
    print(f"{verb} {input_path} ({in_size} bytes) -> {output_path} ({out_size} bytes)")
    if not args.decompress and in_size > 0:
        print(f"ratio: {out_size / in_size:.2%} of original size")

    return 0
