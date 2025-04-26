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
    def __init__(self, chunk_size: int = 64):  # Add chunk_size parameter here
        self.chunk_size = chunk_size
        self.hasher = FileHasher(chunk_size)  # Pass to FileHasher
        self.differ = FileDiffer()

    def analyze_files(self, old_file: str, new_file: str) -> Dict[str, Any]:
        """Analyze two files and return difference report"""
        try:
            logger.info(f"Analyzing files: {old_file} vs {new_file}")
            
            self._validate_file(old_file)
            self._validate_file(new_file)

            old_map = self.hasher.create_chunk_map(old_file)
            new_map = self.hasher.create_chunk_map(new_file)

            diff = self.differ.compare_files(old_map, new_map)
            
            return {
                "success": True,
                "data": self._format_results(diff),
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
        if os.path.getsize(filepath) == 0:
            raise ValueError(f"File is empty: {filepath}")

    def _format_results(self, diff: Dict) -> Dict:
        """Format results with comprehensive statistics"""
        return {
            "summary": {
                "total_chunks": diff["stats"]["total_chunks"],
                "unchanged": diff["stats"]["unchanged"],
                "added": diff["stats"]["added"],
                "removed": diff["stats"]["removed"],
                "modified": diff["stats"]["modified"],
                "changed_percent": diff["stats"]["changed_percent"],
                "bytes_changed": diff["stats"]["bytes_changed"],
                "bytes_added": diff["stats"]["bytes_added"],
                "bytes_removed": diff["stats"]["bytes_removed"],
                "old_size": diff["stats"]["old_size"],
                "new_size": diff["stats"]["new_size"]
            },
            "details": diff
        }

    def generate_sync_plan(self, analysis_result: Dict) -> Dict:
        """Generate detailed synchronization plan"""
        if not analysis_result.get('success', False):
            raise ValueError(f"Cannot generate sync plan: {analysis_result.get('error', 'Unknown error')}")

        data = analysis_result['data']
        sync_plan = {
            "operations": [],
            "total_bytes": data["summary"]["bytes_changed"],
            "efficiency": self._calculate_efficiency(data),
            "estimated_time": self._estimate_sync_time(data["summary"]["bytes_changed"])
        }

        # Process added chunks
        for chunk in data['details'].get('added_chunks', []):
            sync_plan["operations"].append({
                "type": "ADD",
                "offset": chunk['offset'],
                "size": chunk['size'],
                "hash": chunk['hash'][:16],
                "data": chunk.get('data', '')[:100] + "..." if chunk.get('data') else ""
            })

        # Process removed chunks
        for chunk in data['details'].get('removed_chunks', []):
            sync_plan["operations"].append({
                "type": "REMOVE",
                "offset": chunk['offset'],
                "size": chunk['size'],
                "hash": chunk['hash'][:16]
            })

        # Process modified chunks
        for mod in data['details'].get('modified_chunks', []):
            sync_plan["operations"].append({
                "type": "MODIFY",
                "old_offset": mod['old_chunk']['offset'],
                "new_offset": mod['new_chunk']['offset'],
                "size": mod['new_chunk']['size'],
                "old_hash": mod['old_chunk']['hash'][:16],
                "new_hash": mod['new_chunk']['hash'][:16]
            })

        return sync_plan

    def _calculate_efficiency(self, data: Dict) -> float:
        """Calculate sync efficiency percentage"""
        if data["summary"]["new_size"] == 0:
            return 0.0
        return round(
            (1 - (data["summary"]["bytes_changed"] / data["summary"]["new_size"])) * 100,
            2
        )

    def _estimate_sync_time(self, bytes_to_sync: int) -> float:
        """Estimate sync time in seconds (assuming 10MB/s transfer speed)"""
        return round(bytes_to_sync / (10 * 1024 * 1024), 2)