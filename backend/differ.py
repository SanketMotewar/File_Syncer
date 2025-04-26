from typing import Dict, List, Any
import base64

class FileDiffer:
    def compare_files(self, old_map: Dict[str, Any], new_map: Dict[str, Any]) -> Dict[str, Any]:
        result = {
            "unchanged_chunks": [],
            "added_chunks": [],
            "removed_chunks": [],
            "modified_chunks": [],
            "stats": {
                "total_chunks": 0,
                "unchanged": 0,
                "added": 0,
                "removed": 0,
                "modified": 0,
                "changed_percent": 0.0,
                "bytes_changed": 0,
                "bytes_added": 0,
                "bytes_removed": 0,
                "old_size": sum(c['size'] for c in old_map.get('chunks', [])),
                "new_size": sum(c['size'] for c in new_map.get('chunks', []))
            }
        }

        old_chunks = old_map.get('chunks', [])
        new_chunks = new_map.get('chunks', [])
        old_hash_map = {c['hash']: c for c in old_chunks}

        # Track matched chunks
        matched_old = set()
        matched_new = set()

        # First pass - find exact matches
        for new_idx, new_c in enumerate(new_chunks):
            if new_c['hash'] in old_hash_map:
                old_c = old_hash_map[new_c['hash']]
                result["unchanged_chunks"].append(new_c)
                result["stats"]["unchanged"] += 1
                matched_old.add(old_c['index'])
                matched_new.add(new_idx)

        # Second pass - find modified chunks using content comparison
        for new_idx, new_c in enumerate(new_chunks):
            if new_idx in matched_new:
                continue
                
            best_match = None
            best_similarity = 0
            
            for old_c in old_chunks:
                if old_c['index'] in matched_old:
                    continue
                
                # Simple similarity check (could be improved)
                similarity = self.calculate_similarity(old_c['data'], new_c['data'])
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = old_c

            if best_match and best_similarity > 0.7:  # 30% similarity threshold
                result["modified_chunks"].append({
                    "old_chunk": best_match,
                    "new_chunk": new_c
                })
                result["stats"]["modified"] += 1
                result["stats"]["bytes_changed"] += new_c['size']
                matched_old.add(best_match['index'])
                matched_new.add(new_idx)

        # Identify remaining additions and removals
        result["added_chunks"] = [new_c for idx, new_c in enumerate(new_chunks) 
                                if idx not in matched_new]
        result["stats"]["added"] = len(result["added_chunks"])
        result["stats"]["bytes_added"] = sum(c['size'] for c in result["added_chunks"])

        result["removed_chunks"] = [old_c for idx, old_c in enumerate(old_chunks)
                                   if idx not in matched_old]
        result["stats"]["removed"] = len(result["removed_chunks"])
        result["stats"]["bytes_removed"] = sum(c['size'] for c in result["removed_chunks"])

        # Calculate percentages
        total_chunks = max(len(old_chunks), len(new_chunks))  # Use max of both files
        changed = (result["stats"]["added"] + 
                result["stats"]["removed"] + 
                result["stats"]["modified"])
        result["stats"]["changed_percent"] = min(
            (changed / total_chunks) * 100 if total_chunks else 0,
            100.0
        )

        print(f"Change Analysis: {changed}/{total_chunks} chunks changed")
        return result

    @staticmethod
    def calculate_similarity(a: str, b: str) -> float:
        """Basic content similarity score between two base64 strings"""
        a_data = base64.b64decode(a)
        b_data = base64.b64decode(b)
        max_len = max(len(a_data), len(b_data))
        matches = sum(1 for x, y in zip(a_data, b_data) if x == y)
        return matches / max_len if max_len else 0