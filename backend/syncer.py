import os
import logging
from typing import Dict, Any, List
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
        """Analyze two files and return a dict with summary, details, and raw chunk lists."""
        try:
            logger.info(f"Analyzing files: {old_file} vs {new_file}")
            if not os.path.exists(old_file) or not os.path.exists(new_file):
                raise FileNotFoundError("One of the files does not exist")

            old_map = self.hasher.create_chunk_map(old_file)
            new_map = self.hasher.create_chunk_map(new_file)
            diff    = self.differ.compare_files(old_map, new_map)

            formatted = self._format_results(diff)
            # Inject raw chunk lists for plan generation
            formatted["old_chunks"] = old_map["chunks"]
            formatted["new_chunks"] = new_map["chunks"]

            return {"success": True, "data": formatted, "error": None}

        except Exception as e:
            logger.error(f"Analysis failed: {e}", exc_info=True)
            return {"success": False, "data": None, "error": str(e)}

    def _format_results(self, diff: Dict[str, Any]) -> Dict[str, Any]:
        """Only summary + details—chunk arrays added upstream."""
        return {
            "summary": {
                "total_chunks":    diff["stats"]["total_chunks"],
                "unchanged":       diff["stats"]["unchanged"],
                "added":           diff["stats"]["added"],
                "removed":         diff["stats"]["removed"],
                "modified":        diff["stats"]["modified"],
                "changed_percent": diff["stats"]["changed_percent"],
                "bytes_changed":   diff["stats"]["bytes_changed"],
                "bytes_added":     diff["stats"]["bytes_added"],
                "bytes_removed":   diff["stats"]["bytes_removed"],
                "old_size":        diff["stats"]["old_size"],
                "new_size":        diff["stats"]["new_size"],
            },
            "details": diff
        }
    
    def _validate_file(self, path: str):
        if not os.path.exists(path): raise FileNotFoundError(path)
        if not os.access(path, os.R_OK): raise PermissionError(path)
        if os.path.getsize(path) == 0:       raise ValueError(f"Empty file: {path}")

    def _format_results(self, diff: Dict[str, Any]) -> Dict[str, Any]:
        stats = diff['stats']
        return {
            "summary": {
                "total_chunks":   stats["total_chunks"],
                "unchanged":      stats["unchanged"],
                "added":          stats["added"],
                "removed":        stats["removed"],
                "modified":       stats["modified"],
                "changed_percent":stats["changed_percent"],
                "bytes_changed":  stats["bytes_changed"],
                "bytes_added":    stats["bytes_added"],
                "bytes_removed":  stats["bytes_removed"],
                "old_size":       stats["old_size"],
                "new_size":       stats["new_size"]
            },
            "details": diff
        }

    def generate_sync_plan(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Turn the analysis into a sequence of ADD/MODIFY/UNCHANGED ops + a removes list."""
        data    = analysis["data"]
        details = data.get("details", {})

        # Defensive checks
        if "old_chunks" not in data or "new_chunks" not in data:
            logger.error("Missing chunk lists in analysis data: %r", data.keys())
            raise KeyError("old_chunks/new_chunks missing")

        old_chunks = data["old_chunks"]
        new_chunks = data["new_chunks"]

        unchanged_hashes = {c["hash"] for c in details.get("unchanged_chunks", [])}
        mod_map = {m["new_chunk"]["hash"]: m for m in details.get("modified_chunks", [])}

        ops = []
        last_end = 0

        # 1) Walk new_chunks, emit UNCHANGED / MODIFY / ADD
        for chunk in new_chunks:
            off, sz, h = chunk["offset"], chunk["size"], chunk["hash"]
            if off > last_end:
                ops.append({"type": "UNCHANGED", "offset": last_end, "size": off - last_end})

            if h in unchanged_hashes:
                ops.append({"type":"UNCHANGED","offset":off,"size":sz})
            elif h in mod_map:
                nc = mod_map[h]["new_chunk"]
                ops.append({
                    "type":   "MODIFY",
                    "offset": nc["offset"],
                    "size":   nc["size"],
                    "data":   nc["data"]
                })
            else:
                ops.append({
                    "type":   "ADD",
                    "offset": off,
                    "size":   sz,
                    "data":   chunk["data"]
                })

            last_end = off + sz

        # 2) If new file shorter than old, tail is UNCHANGED
        summary = data["summary"]
        new_end = (new_chunks[-1]["offset"] + new_chunks[-1]["size"]) if new_chunks else 0
        if new_end < summary["old_size"]:
            ops.append({"type":"UNCHANGED","offset":new_end,"size":summary["old_size"]-new_end})

        # 3) Collect REMOVEs for any old chunk not matched
        matched_old = {c["index"] for c in details.get("unchanged_chunks", [])}
        matched_old |= {m["old_chunk"]["index"] for m in details.get("modified_chunks", [])}
        removes = [
            {"type":"REMOVE","offset":oc["offset"],"size":oc["size"]}
            for oc in old_chunks
            if oc["index"] not in matched_old
        ]

        return {
            "operations":     ops,
            "changes":        sorted([o for o in ops if o["type"]!="UNCHANGED"] + removes,
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
        # assuming 10MB/s
        return round(bytes_to_sync / (10 * 1024 * 1024), 2)
    