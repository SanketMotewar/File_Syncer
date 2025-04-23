import os
from typing import List, Dict, Any, Tuple

class FileChunker:
    def __init__(self, chunk_size: int = 16, window_size: int = 48):
        self.chunk_size = chunk_size
        self.window_size = window_size

    def chunk_file(self, file_path: str) -> List[Dict[str, Any]]:
        """Split file into fixed-size chunks with metadata"""
        print(f"Chunking file: {file_path}")  # Debugging statement
        chunks = []
        if not os.path.exists(file_path):
            return chunks

        with open(file_path, 'rb') as f:
            offset = 0
            while True:
                chunk_data = f.read(self.chunk_size)
                if not chunk_data:
                    break
                chunks.append({
                    "offset": offset,
                    "size": len(chunk_data),
                    "data": chunk_data
                })
                offset += len(chunk_data)

        # Log the chunks for debugging
        for chunk in chunks:
            print(f"Chunk: offset={chunk['offset']}, size={chunk['size']}, data={chunk['data'][:20]}...")

        return chunks

    def chunk_file_rolling(self, file_path: str) -> List[Tuple[int, int]]:
        """Split file using rolling hash for content-defined chunking"""
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
        while i < n - self.window_size:
            window = data[i:i+self.window_size]
            hash_val = self._rolling_hash(window)

            j = i + self.window_size
            while j < n:
                if self._is_boundary(hash_val):
                    chunks.append((i, j))
                    i = j
                    break
                if j < n - 1:
                    hash_val = self._update_rolling_hash(hash_val, data[j], data[j-self.window_size])
                j += 1
            else:
                chunks.append((i, n))
                break

        return chunks

    def _rolling_hash(self, data: bytes) -> int:
        """Simple rolling hash implementation"""
        prime = 31
        mod = 1 << 32
        hash_val = 0
        for byte in data:
            hash_val = (hash_val * prime + byte) % mod
        return hash_val

    def _update_rolling_hash(self, current_hash: int, new_byte: int, old_byte: int) -> int:
        """Update rolling hash value"""
        prime = 31
        mod = 1 << 32
        window_size = self.window_size
        return (current_hash * prime - old_byte * (prime ** window_size) + new_byte) % mod

    def _is_boundary(self, hash_val: int) -> bool:
        """Determine if hash value indicates a chunk boundary"""
        return (hash_val & 0xFFFF) == 0
