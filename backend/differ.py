from typing import Dict, List, Any

class FileDiffer:
    def compare_files(self, old_map: Dict[str, Any], new_map: Dict[str, Any]) -> Dict[str, Any]:
        result = {
            "unchanged_chunks": [],
            "added_chunks": [],
            "removed_chunks": [],
            "modified_chunks": [],
            "stats": {
                "total_chunks": len(new_map.get('chunks', [])),
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

        # Find matching chunks
        for new_idx, new_chunk in enumerate(new_chunks):
            matched = False
            for old_idx, old_chunk in enumerate(old_chunks):
                if new_chunk['hash'] == old_chunk['hash']:
                    result["unchanged_chunks"].append(new_chunk)
                    result["stats"]["unchanged"] += 1
                    matched = True
                    break
            
            if not matched:
                # Check for modified chunks (similar position but different hash)
                for old_chunk in old_chunks:
                    if abs(new_chunk['offset'] - old_chunk['offset']) < 10:  # Similar position
                        result["modified_chunks"].append({
                            "old_chunk": old_chunk,
                            "new_chunk": new_chunk
                        })
                        result["stats"]["modified"] += 1
                        result["stats"]["bytes_changed"] += new_chunk['size']
                        matched = True
                        break
                
                if not matched:
                    result["added_chunks"].append(new_chunk)
                    result["stats"]["added"] += 1
                    result["stats"]["bytes_added"] += new_chunk['size']

        # Find removed chunks
        for old_chunk in old_chunks:
            if not any(c['hash'] == old_chunk['hash'] for c in new_chunks):
                result["removed_chunks"].append(old_chunk)
                result["stats"]["removed"] += 1
                result["stats"]["bytes_removed"] += old_chunk['size']

        # Calculate changed percentage
        total_changes = result["stats"]["added"] + result["stats"]["removed"] + result["stats"]["modified"]
        result["stats"]["changed_percent"] = (total_changes / result["stats"]["total_chunks"]) * 100

        print("Comparison Result:", result)
        return result