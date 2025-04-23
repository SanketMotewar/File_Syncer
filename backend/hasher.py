import os
import hashlib
import base64
from typing import Dict, List, Any
from .chunker import FileChunker

class FileHasher:
    def __init__(self):
        self.chunker = FileChunker()

    @staticmethod
    def sha256_hash(data: bytes) -> str:
        """Generate SHA-256 hash of data"""
        return hashlib.sha256(data).hexdigest()

    def create_chunk_map(self, file_path: str, chunk_size: int = 16, window_size: int = 48) -> Dict[str, Any]:
        """
        Create a complete chunk map with hashes and metadata
        Returns: {
            "filepath": str,
            "chunks": [
                {
                    "index": int,
                    "offset": int,
                    "size": int,
                    "hash": str,
                    "data": str (base64 encoded)
                },
                ...
            ],
            "hashes": List[str]
        }
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        self.chunker = FileChunker(chunk_size, window_size)
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
                    "data": base64.b64encode(chunk_data).decode('utf-8'),  # Convert to base64
                    "filepath": file_path
                })
                hashes.append(chunk_hash)

        # Log the chunk info for debugging
        print(f"Chunk info for {file_path}: {chunk_info}")

        return {
            "filepath": file_path,
            "chunks": chunk_info,
            "hashes": hashes
        }
