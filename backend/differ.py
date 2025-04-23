from typing import Dict, List, Any
from collections import defaultdict

class FileDiffer:
    def compare_files(self, old_map: Dict[str, Any], new_map: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare two file chunk maps and return differences
        Returns: {
            "unchanged_chunks": List[Dict],
            "added_chunks": List[Dict],
            "removed_chunks": List[Dict],
            "modified_chunks": List[Dict],
            "stats": {
                "total_chunks": int,
                "changed_percentage": float,
                "bytes_changed": int
            }
        }
        """
        result = {
            "unchanged_chunks": [],
            "added_chunks": [],
            "removed_chunks": [],
            "modified_chunks": [],
            "stats": {
                "total_chunks": 0,
                "changed_percentage": 0.0,
                "bytes_changed": 0
            }
        }

        # Create quick lookup maps
        old_hash_map = {chunk['hash']: chunk for chunk in old_map.get('chunks', [])}
        new_hash_map = {chunk['hash']: chunk for chunk in new_map.get('chunks', [])}

        # Log the hash maps for debugging
        print("Old Hash Map:", old_hash_map)
        print("New Hash Map:", new_hash_map)

        # Find common and unique hashes
        common_hashes = set(old_hash_map.keys()) & set(new_hash_map.keys())
        added_hashes = set(new_hash_map.keys()) - set(old_hash_map.keys())
        removed_hashes = set(old_hash_map.keys()) - set(new_hash_map.keys())

        # Process unchanged chunks
        for hash_val in common_hashes:
            result["unchanged_chunks"].append(new_hash_map[hash_val])

        # Process added chunks
        for hash_val in added_hashes:
            result["added_chunks"].append(new_hash_map[hash_val])

        # Process removed chunks
        for hash_val in removed_hashes:
            result["removed_chunks"].append(old_hash_map[hash_val])

        # Calculate statistics
        total_chunks = len(new_map.get('chunks', []))
        changed_chunks = (len(result["added_chunks"]) +
                          len(result["removed_chunks"]))

        bytes_changed = sum(c["size"] for c in result["added_chunks"])
        bytes_changed += sum(c["size"] for c in result["removed_chunks"])

        result["stats"] = {
            "total_chunks": total_chunks,
            "changed_percentage": (changed_chunks / total_chunks * 100) if total_chunks > 0 else 0,
            "bytes_changed": bytes_changed
        }

        # Log the result for debugging
        print("Comparison Result:", result)

        return result
