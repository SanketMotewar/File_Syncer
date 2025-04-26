import os
import hashlib
import base64
from typing import Dict, List, Any, Tuple
from .chunker import FileChunker

class FileHasher:
    def __init__(self, avg_chunk_size: int = 16):
        self.chunker = FileChunker(avg_chunk_size)
        self.text_extensions = {'.txt', '.log', '.csv', '.json', '.xml'}

    @staticmethod
    def sha256_hash(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def is_text_file(self, file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext in self.text_extensions

    def create_chunk_map(self, file_path: str) -> Dict[str, Any]:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Use line-based chunking for small text files
        if self.is_text_file(file_path) and os.path.getsize(file_path) < 1024:
            chunks = self.line_based_chunks(file_path)
        else:
            chunks = self.chunker.chunk_file_rolling(file_path)

        chunk_info = []
        hashes = []

        for i, (start, end) in enumerate(chunks):
            with open(file_path, 'rb') as f:
                f.seek(start)
                chunk_data = f.read(end - start)
                chunk_hash = self.sha256_hash(chunk_data)
                chunk_info.append({
                    "index": i,
                    "offset": start,
                    "size": end - start,
                    "hash": chunk_hash,
                    "data": base64.b64encode(chunk_data).decode('utf-8'),
                    "filepath": file_path
                })
                hashes.append(chunk_hash)

        return {
            "filepath": file_path,
            "chunks": chunk_info,
            "hashes": hashes
        }

    def line_based_chunks(self, file_path: str) -> List[Tuple[int, int]]:
        chunks = []
        with open(file_path, 'rb') as f:
            pos = 0
            while True:
                line = f.readline()
                if not line:
                    break
                end = pos + len(line)
                chunks.append((pos, end))
                pos = end
        return chunks