import os
import logging
from typing import Dict, List, Any
from pathlib import Path
from .chunker import FileChunker
from .hasher import FileHasher
from .differ import FileDiffer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FileSyncer:
    def __init__(self, chunk_size: int = 16, window_size: int = 48):
        self.chunk_size = chunk_size
        self.window_size = window_size
        self.chunker = FileChunker(chunk_size, window_size)
        self.hasher = FileHasher()
        self.differ = FileDiffer()

    def analyze_files(self, old_file: str, new_file: str) -> Dict[str, Any]:
        """Analyze two files and return difference report"""
        try:
            logger.info(f"Analyzing files: {old_file} vs {new_file}")

            # Validate files
            self._validate_file(old_file)
            self._validate_file(new_file)

            # Generate chunk maps
            old_map = self.hasher.create_chunk_map(old_file, self.chunk_size, self.window_size)
            new_map = self.hasher.create_chunk_map(new_file, self.chunk_size, self.window_size)

            # Compare files
            diff = self.differ.compare_files(old_map, new_map)

            return {
                "success": True,
                "data": self._format_results(diff, old_map, new_map),
                "error": None
            }
        except Exception as e:
            logger.error(f"Analysis failed: {str(e)}", exc_info=True)
            return {
                "success": False,
                "data": None,
                "error": str(e)
            }

    def _validate_file(self, filepath: str) -> None:
        """Validate file exists and is readable"""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"File not found: {filepath}")
        if not os.access(filepath, os.R_OK):
            raise PermissionError(f"Cannot read file: {filepath}")

    def _format_results(self, diff: Dict, old_map: Dict, new_map: Dict) -> Dict:
        """Format results with proper statistics"""
        total_chunks = len(new_map.get('chunks', []))
        changed = (len(diff.get("added_chunks", [])) +
                   len(diff.get("removed_chunks", [])))

        return {
            "summary": {
                "total_chunks": total_chunks,
                "unchanged": len(diff.get("unchanged_chunks", [])),
                "added": len(diff.get("added_chunks", [])),
                "removed": len(diff.get("removed_chunks", [])),
                "modified": len(diff.get("modified_chunks", [])),
                "changed_percent": min(100.0, (changed / total_chunks * 100)) if total_chunks > 0 else 0.0,
            },
            "file_stats": {
                "old_size": sum(c['size'] for c in old_map.get('chunks', [])),
                "new_size": sum(c['size'] for c in new_map.get('chunks', [])),
            },
            "chunk_size": self.chunk_size,
            "details": diff
        }

    def generate_sync_plan(self, analysis_result: Dict) -> Dict:
        """Generate synchronization plan from analysis results"""
        if not analysis_result.get('success', False):
            error = analysis_result.get('error', 'Unknown error')
            raise ValueError(f"Cannot generate sync plan: {error}")

        data = analysis_result['data']
        sync_plan = {
            "operations": [],
            "total_bytes": 0,
            "efficiency": 0.0,
            "estimated_time": 0.0
        }

        # Process added chunks
        for chunk in data['details'].get('added_chunks', []):
            sync_plan["operations"].append({
                "type": "ADD",
                "offset": chunk['offset'],
                "size": chunk['size'],
                "hash": chunk['hash'][:16]  # Truncated for display
            })
            sync_plan["total_bytes"] += chunk['size']

        # Calculate efficiency
        total_size = data['file_stats']['new_size']
        if total_size > 0:
            sync_plan["efficiency"] = round(
                (total_size - sync_plan["total_bytes"]) / total_size * 100, 2
            )

        # Estimate time (10MB/s transfer speed)
        sync_plan["estimated_time"] = round(
            sync_plan["total_bytes"] / (10 * 1024 * 1024), 2
        )

        return sync_plan

    def sync_files(self, source: str, target: str, output: str) -> Dict:
        """Perform file synchronization"""
        try:
            analysis = self.analyze_files(source, target)
            if not analysis['success']:
                return analysis

            sync_plan = self.generate_sync_plan(analysis)

            # Create output directory if needed
            Path(output).parent.mkdir(parents=True, exist_ok=True)

            # In a real implementation, apply the sync plan here
            # For now, just copy the target file to output
            with open(target, 'rb') as src, open(output, 'wb') as dest:
                dest.write(src.read())

            return {
                "success": True,
                "sync_plan": sync_plan,
                "error": None
            }
        except Exception as e:
            logger.error(f"Sync failed: {str(e)}", exc_info=True)
            return {
                "success": False,
                "sync_plan": None,
                "error": str(e)
            }

    def get_chunk_size(self) -> int:
        return self.chunk_size

    def set_chunk_size(self, size: int):
        if size <= 0:
            raise ValueError("Chunk size must be positive")
        self.chunk_size = size
        self.chunker = FileChunker(size, self.window_size)

