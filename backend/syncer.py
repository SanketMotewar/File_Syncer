import os
import logging
import base64
from typing import Dict, Any, List
from pathlib import Path
from .chunker import FileChunker
from .hasher import FileHasher
from .differ import FileDiffer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FileSyncer:
    def __init__(self, chunk_size: int = 16):
        self.chunk_size = chunk_size
        self.hasher = FileHasher(chunk_size)
        self.differ = FileDiffer()

    def analyze_files(self, old_file: str, new_file: str) -> Dict[str, Any]:
        """Analyze two files and return difference report plus raw chunk lists."""
        try:
            logger.info(f"Analyzing: {old_file} vs {new_file}")
            old_map = self.hasher.create_chunk_map(old_file)
            new_map = self.hasher.create_chunk_map(new_file)
            diff    = self.differ.compare_files(old_map, new_map)

            formatted = self._format_results(diff)
            # Inject raw chunks so generate_sync_plan can use their offsets/sizes/data
            formatted["old_chunks"] = old_map["chunks"]
            formatted["new_chunks"] = new_map["chunks"]

            return {"success": True, "data": formatted, "error": None}
        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            return {"success": False, "data": None, "error": str(e)}

    def _format_results(self, diff: Dict[str, Any]) -> Dict[str, Any]:
        stats = diff["stats"]
        return {
            "summary": {
                "total_chunks":    stats["total_chunks"],
                "unchanged":       stats["unchanged"],
                "added":           stats["added"],
                "removed":         stats["removed"],
                "modified":        stats["modified"],
                "changed_percent": stats["changed_percent"],
                "bytes_changed":   stats["bytes_changed"],
                "bytes_added":     stats["bytes_added"],
                "bytes_removed":   stats["bytes_removed"],
                "old_size":        stats["old_size"],
                "new_size":        stats["new_size"],
            },
            "details": diff
        }

    def generate_sync_plan(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build a sequence of operations (UNCHANGED, ADD, MODIFY, REMOVE),
        where each UNCHANGED carries its exact bytes (base64-encoded).
        """
        data     = analysis["data"]
        details  = data["details"]
        old_chunks = data.get("old_chunks", [])
        new_chunks = data.get("new_chunks", [])

        # load old file bytes so we can slice out UNCHANGED segments
        if old_chunks:
            old_file_path = old_chunks[0]["filepath"]
            old_bytes = Path(old_file_path).read_bytes()
        else:
            old_bytes = b""

        unchanged_hashes = {c["hash"] for c in details.get("unchanged_chunks", [])}
        mod_map = {m["new_chunk"]["hash"]: m for m in details.get("modified_chunks", [])}

        ops = []
        last_end = 0

        # 1) Walk the new file's chunks in order
        for chunk in new_chunks:
            off, sz, h = chunk["offset"], chunk["size"], chunk["hash"]

            # if there's a gap of bytes between last_end and this chunk → still UNCHANGED
            if off > last_end:
                segment = old_bytes[last_end:off]
                ops.append({
                    "type":   "UNCHANGED",
                    "offset": last_end,
                    "size":   off - last_end,
                    "data":   base64.b64encode(segment).decode("utf-8")
                })

            if h in unchanged_hashes:
                segment = old_bytes[off:off+sz]
                ops.append({
                    "type":   "UNCHANGED",
                    "offset": off,
                    "size":   sz,
                    "data":   base64.b64encode(segment).decode("utf-8")
                })

            elif h in mod_map:
                nc = mod_map[h]["new_chunk"]
                # new_chunk.data is already base64
                ops.append({
                    "type":   "MODIFY",
                    "offset": nc["offset"],
                    "size":   nc["size"],
                    "data":   nc["data"]
                })

            else:
                # entirely new chunk
                ops.append({
                    "type":   "ADD",
                    "offset": off,
                    "size":   sz,
                    "data":   chunk["data"]
                })

            last_end = off + sz

        # 2) if new file ends before old file, copy the tail as unchanged
        summary = data["summary"]
        old_size = summary["old_size"]
        if last_end < old_size:
            tail = old_bytes[last_end:old_size]
            ops.append({
                "type":   "UNCHANGED",
                "offset": last_end,
                "size":   old_size - last_end,
                "data":   base64.b64encode(tail).decode("utf-8")
            })

        # 3) For completeness, collect REMOVEs (not strictly needed to rebuild,
        #    but useful for UI to show what's gone)
        matched_old = {c["index"] for c in details.get("unchanged_chunks", [])}
        matched_old |= {m["old_chunk"]["index"] for m in details.get("modified_chunks", [])}
        removes = [
            {"type": "REMOVE", "offset": oc["offset"], "size": oc["size"]}
            for oc in old_chunks
            if oc["index"] not in matched_old
        ]

        return {
            "operations":     ops,
            "changes":        sorted([o for o in ops if o["type"] != "UNCHANGED"] + removes,
                                     key=lambda o: o["offset"]),
            "total_bytes":    summary["bytes_changed"],
            "efficiency":     self._calculate_efficiency(summary),
            "estimated_time": self._estimate_sync_time(summary["bytes_changed"])
        }

    def _calculate_efficiency(self, summary: Dict[str, Any]) -> float:
        new_size = summary.get("new_size", 0)
        changed  = summary.get("bytes_changed", 0)
        return round((1 - (changed / new_size)) * 100, 2) if new_size else 0.0

    def _estimate_sync_time(self, bytes_to_sync: int) -> float:
        # assume 10 MB/s
        return round(bytes_to_sync / (10 * 1024 * 1024), 2)
