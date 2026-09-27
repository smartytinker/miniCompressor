"""MSB-first bit-level I/O for packing variable-length Huffman codes into bytes."""


class BitWriter:
    def __init__(self):
        self._bytes = bytearray()
        self._current = 0
        self._nbits = 0

    def write_bits(self, value: int, nbits: int) -> None:
        """Append the low `nbits` bits of `value`, most-significant bit first."""
        for i in range(nbits - 1, -1, -1):
            self._current = (self._current << 1) | ((value >> i) & 1)
            self._nbits += 1
            if self._nbits == 8:
                self._bytes.append(self._current)
                self._current = 0
                self._nbits = 0

    def write_code(self, code: str) -> None:
        """Append a code given as a string of '0'/'1' characters."""
        for ch in code:
            self.write_bits(1 if ch == "1" else 0, 1)

    def total_bits(self) -> int:
        return len(self._bytes) * 8 + self._nbits

    def getvalue(self) -> bytes:
        """Return the bytes written so far, padding the final byte with zero bits."""
        if self._nbits == 0:
            return bytes(self._bytes)
        padded = self._current << (8 - self._nbits)
        return bytes(self._bytes) + bytes([padded])


class BitReader:
    def __init__(self, data: bytes, total_bits: int):
        self._data = data
        self._total_bits = total_bits
        self._pos = 0

    def read_bit(self) -> int:
        if self._pos >= self._total_bits:
            raise EOFError("no more bits to read")
        byte = self._data[self._pos // 8]
        bit = (byte >> (7 - (self._pos % 8))) & 1
        self._pos += 1
        return bit

    def read_bits(self, nbits: int) -> int:
        value = 0
        for _ in range(nbits):
            value = (value << 1) | self.read_bit()
        return value

    def has_more(self) -> bool:
        return self._pos < self._total_bits
