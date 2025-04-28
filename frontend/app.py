import os
import sys
import time
import base64
import shutil
import logging
import textwrap
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename


logging.basicConfig(level=logging.DEBUG)
sys.path.append(str(Path(__file__).parent.parent))
from backend.syncer import FileSyncer

# Initialize Flask app
BASE_DIR = Path(__file__).parent.parent
app = Flask(
    __name__,
    template_folder=str(BASE_DIR / 'frontend' / 'templates'),
    static_folder=str(BASE_DIR / 'frontend' / 'static')
)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.secret_key = 'your-secret-key'
Path(app.config['UPLOAD_FOLDER']).mkdir(exist_ok=True)

def apply_sync_plan(old_file_path: str, sync_plan: dict, output_file_path: str):
    """
    Rebuilds the new file exactly according to sync_plan['operations'].
    
    sync_plan format:
      {
        "operations": [
           {"type":"UNCHANGED","offset":int,"size":int},
           {"type":"ADD",      "offset":int,"size":int,"data":base64str},
           {"type":"MODIFY",   "offset":int,"size":int,"data":base64str},
           {"type":"REMOVE",   "offset":int,"size":int},
           ...
        ],
        ...
      }
    """
    # Load entire old file
    old_data = Path(old_file_path).read_bytes()
    new_data = bytearray()

    for op in sync_plan.get("operations", []):
        t = op["type"]
        if t == "UNCHANGED":
            # Copy chunk from old
            off, sz = op["offset"], op["size"]
            new_data.extend(old_data[off : off + sz])

        elif t in ("ADD", "MODIFY"):
            # Decode and append new/modified bytes
            new_data.extend(base64.b64decode(op["data"]))

        elif t == "REMOVE":
            # Skip these bytes entirely
            continue

        else:
            raise ValueError(f"Unknown operation type: {t}")

    # Write the reconstructed file
    Path(output_file_path).write_bytes(new_data)

def determine_chunk_size(file_size: int) -> int:
    if file_size < 512:
        return 8
    if file_size < 1024 * 1024:
        return 512
    if file_size < 10 * 1024 * 1024:
        return 4096
    return 8192

def prepare_visualization(diff_report: dict) -> list:
    colors = {"added":"#4CAF50","removed":"#F44336","unchanged":"#9E9E9E","modified":"#FFC107"}
    viz = []
    for m in diff_report.get("details",{}).get("modified_chunks",[]):
        nc=m["new_chunk"]
        viz.append({ "index":nc["index"],"type":"modified","size":nc["size"],
                     "color":colors["modified"],"old_offset":m["old_chunk"]["offset"],
                     "new_offset":nc["offset"] })
    for c in diff_report.get("details",{}).get("added_chunks",[]):
        viz.append({ "index":c["index"],"type":"added","size":c["size"],
                     "color":colors["added"],"offset":c["offset"] })
    for c in diff_report.get("details",{}).get("removed_chunks",[]):
        viz.append({ "index":c["index"],"type":"removed","size":c["size"],
                     "color":colors["removed"],"offset":c["offset"] })
    for c in diff_report.get("details",{}).get("unchanged_chunks",[]):
        viz.append({ "index":c["index"],"type":"unchanged","size":c["size"],
                     "color":colors["unchanged"],"offset":c["offset"] })
    viz.sort(key=lambda x: x["index"])
    return viz

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/compare', methods=['POST'])
def compare_files():
    try:
        if 'old_file' not in request.files or 'new_file' not in request.files:
            return jsonify(status="error", message="Both files required"), 400

        old_f = request.files['old_file']
        new_f = request.files['new_file']
        if not old_f.filename or not new_f.filename:
            return jsonify(status="error", message="No files selected"), 400

        old_fn = secure_filename(old_f.filename)
        new_fn = secure_filename(new_f.filename)
        UP = Path(app.config['UPLOAD_FOLDER'])
        old_path = UP/old_fn
        new_path = UP/new_fn
        old_f.save(str(old_path))
        new_f.save(str(new_path))

        size = max(old_path.stat().st_size, new_path.stat().st_size)
        cs = determine_chunk_size(size)
        syncer = FileSyncer(chunk_size=cs)

        start = time.time()
        res = syncer.analyze_files(str(old_path), str(new_path))
        if not res.get("success", False):
            return jsonify(status="error", message=res.get("error", "Analysis failed")), 400

        # Now call generate_sync_plan here to get the sync operations
        plan = syncer.generate_sync_plan(res)
        viz  = prepare_visualization(res["data"])

        # write analysis file
        try:
            txt = generate_human_readable_analysis(
                old_fn, new_fn,
                res["data"],     # <-- diff_data
                plan
            )
            af = UP / f"analysis_{int(time.time())}.txt"
            af.write_text(txt, encoding="utf-8")
            analysis_file = af.name
        except Exception:
            logging.exception("Failed to write analysis file")
            analysis_file = None

        return jsonify({
            "status":       "success",
            "diff_report":  res["data"],
            "sync_plan":    plan,
            "visualization":viz,
            "analysis_file":analysis_file,
            # …
        })

    except Exception:
        logging.exception("Error in /compare")
        return jsonify(status="error", message="Internal server error"), 500
    
def extract_chunks(self, file_path: str) -> list:
        """
        Extract chunks from the given file. Each chunk is a dictionary containing:
        - offset: the starting position of the chunk in the file
        - size: the size of the chunk
        - hash: a unique hash representing the content of the chunk
        - data: the chunk's actual data (for ADD operations)
        """
        chunks = []
        with open(file_path, 'rb') as file:
            offset = 0
            while chunk := file.read(self.chunk_size):
                # Generate hash for this chunk
                chunk_hash = hashlib.sha256(chunk).hexdigest()
                chunks.append({
                    "offset": offset,
                    "size": len(chunk),
                    "hash": chunk_hash,
                    "data": chunk  # Optional: store data if needed for "ADD" operations
                })
                offset += len(chunk)
        
        return chunks

# 🔥 Helper function to generate human-readable analysis
def generate_human_readable_analysis(old_fn, new_fn, diff_data, sync_plan):
    """
    A concise analysis report.
    - Lists old/new chunks (in index order).
    - References them from diff_data['old_chunks'] / ['new_chunks'].
    - Shows each operation in the sync_plan.
    """
    lines = []
    lines.append(f"Old File: {old_fn}")
    lines.append(f"New File: {new_fn}")
    lines.append("=" * 50)

    # Summary
    s = diff_data["summary"]
    lines.append("=== Summary ===")
    lines.append(f"Total Chunks : {s['total_chunks']}")
    lines.append(f"Unchanged    : {s['unchanged']}")
    lines.append(f"Added        : {s['added']} ({s['bytes_added']} bytes)")
    lines.append(f"Removed      : {s['removed']} ({s['bytes_removed']} bytes)")
    lines.append(f"Modified     : {s['modified']}")
    lines.append(f"Change%      : {s['changed_percent']:.1f}%")
    lines.append("")

    def fmt_chunks(chunks, title):
        lines.append(f"=== {title} ===")
        for c in sorted(chunks, key=lambda c: c["index"]):
            # decode once
            raw = base64.b64decode(c["data"])
            txt = raw.decode("utf-8", errors="replace")
            # show embedded newlines as ↵, strip
            single = txt.replace("\r\n", "\n").replace("\n", "↵").strip()
            lines.append(f"Chunk {c['index'] + 1}: {single}")
        lines.append("")

    # **Use top‐level** old_chunks / new_chunks, not diff_data["details"]
    fmt_chunks(diff_data.get("old_chunks", []), "Old File Chunks")
    fmt_chunks(diff_data.get("new_chunks", []), "New File Chunks")

    # Sync Plan
    lines.append("=== Synchronization Plan ===")
    lines.append(f"Total Ops : {len(sync_plan['operations'])}")
    lines.append(f"Efficiency : {sync_plan['efficiency']:.1f}%")
    lines.append("")

    for i, op in enumerate(sync_plan["operations"], 1):
        t   = op["type"]
        off = op["offset"]
        sz  = op["size"]

        if t == "UNCHANGED":
            lines.append(f"{i}. UNCHANGED @offset {off:<3} size {sz}")
        elif t == "REMOVE":
            lines.append(f"{i}. REMOVE    @offset {off:<3} size {sz}")
        else:  # ADD or MODIFY
            label = "ADD" if t == "ADD" else "MODIFY"
            # try to grab a one‐line snippet
            snippet = ""
            b64     = op.get("data") or op.get("new_data", "")
            try:
                raw = base64.b64decode(b64)
                txt = raw.decode("utf-8", errors="replace").splitlines()[0].strip()
                snippet = txt
            except:
                pass

            lines.append(f"{i}. {label:8}@offset {off:<3} size {sz}")
            if snippet:
                wrapped = textwrap.fill(snippet, width=60)
                for ln in wrapped.splitlines():
                    lines.append(f"    → {ln}")
        lines.append("")

    return "\n".join(lines)

@app.route('/analysis/<filename>')
def serve_analysis_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/synchronize', methods=['POST'])
def synchronize_files():
    try:
        data = request.get_json(force=True)
        old_fn = data.get("old_file") or data.get("old_filename")
        ops    = data.get("operations")

        # Key must exist (even an empty list is OK)
        if old_fn is None:
            return jsonify(status="error", message="Missing 'old_file'"), 400
        if ops is None:
            return jsonify(status="error", message="Missing 'operations'"), 400

        UP       = Path(app.config['UPLOAD_FOLDER'])
        old_path = UP / old_fn
        if not old_path.exists():
            return jsonify(status="error", message="Old file not found"), 404

        # Read entire old file once
        old_data = old_path.read_bytes()
        new_data = bytearray()

        # Sort operations by offset to assemble in order
        for op in sorted(ops, key=lambda o: o.get("offset", 0)):
            t   = (op.get("type") or "").upper()
            off = int(op.get("offset", 0))
            sz  = int(op.get("size",    0))

            if t == "UNCHANGED":
                # copy a slice from the old file
                new_data.extend(old_data[off:off+sz])

            elif t == "ADD":
                # append the new bytes
                b64 = op.get("data", "")
                try:
                    new_data.extend(base64.b64decode(b64))
                except:
                    logging.warning("Bad base64 in ADD op at offset %s", off)

            elif t == "MODIFY":
                # replace old slice with new bytes
                b64 = op.get("new_data", op.get("data", ""))
                try:
                    new_data.extend(base64.b64decode(b64))
                except:
                    logging.warning("Bad base64 in MODIFY op at offset %s", off)

            elif t == "REMOVE":
                # skip this slice (do nothing)
                continue

            else:
                # unknown op → skip safely
                logging.warning("Skipping unknown op %r", op)

        # Write out the reconstructed file
        synced_path = UP / f"synced_{old_fn}"
        synced_path.write_bytes(new_data)

        return jsonify(
            status="success",
            message="Files synchronized successfully",
            output_file=synced_path.name
        )

    except Exception as e:
        logging.exception("Error in /synchronize")
        return jsonify(status="error", message="Internal server error"), 500
    
@app.route('/uploads/<filename>')
def serve_uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)