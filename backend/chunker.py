import os
from typing import List, Dict, Any, Tuple

class FileChunker:
    def __init__(self, avg_chunk_size: int = 64, window_size: int = 48):
        self.avg_chunk_size = avg_chunk_size
        self.window_size = window_size
        self.prime = 31
        self.mod = 1 << 32

    def chunk_file_rolling(self, file_path: str) -> List[Tuple[int, int]]:
        """Improved content-defined chunking"""
        chunks = []
        if not os.path.exists(file_path):
            return chunks

        with open(file_path, 'rb') as f:
            data = f.read()

        if not data:
            return chunks

        n = len(data)
        if n <= self.window_size:
            return [(0, n)]

        i = 0
        min_chunk = self.avg_chunk_size // 2
        max_chunk = self.avg_chunk_size * 2

        while i < n:
            chunk_start = i
            chunk_end = min(i + max_chunk, n)
            boundary = self._find_boundary(data, chunk_start, chunk_end)
            chunks.append((chunk_start, boundary))
            i = boundary

        return chunks

    def _find_boundary(self, data: bytes, start: int, end: int) -> int:
        """Find a rolling-hash boundary, then snap forward to the next newline if possible."""
        if end - start <= self.window_size:
            return end

        # initial hash
        window = data[start:start + self.window_size]
        hash_val = self._rolling_hash(window)

        for i in range(start + self.window_size, end):
            if (hash_val % self.avg_chunk_size) == (self.avg_chunk_size - 1):
                # we found a “raw” boundary at i — now try to include through the next '\n'
                scan_end = min(end, i + self.window_size)
                nl = data.find(b'\n', i, scan_end)
                return (nl + 1) if nl != -1 else i

            # update rolling hash
            hash_val = self._update_rolling_hash(
                hash_val,
                data[i],
                data[i - self.window_size]
            )

        return end

    def _rolling_hash(self, data: bytes) -> int:
        """Calculate initial rolling hash"""
        hash_val = 0
        for i, byte in enumerate(data):
            hash_val = (hash_val * self.prime + byte) % self.mod
        return hash_val

    def _update_rolling_hash(self, current_hash: int, new_byte: int, old_byte: int) -> int:
        """Update rolling hash efficiently"""
        power = pow(self.prime, self.window_size - 1, self.mod)
        return ((current_hash - old_byte * power) * self.prime + new_byte) % self.mod  # Fixed parentheses