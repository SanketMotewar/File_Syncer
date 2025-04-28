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

@app.route("/synchronize", methods=["POST"])
def synchronize():
    sync_plan = request.get_json()

    output_path = "uploads/synced_old_version.txt"  # Updated filename

    content = bytearray()
    for op in sync_plan["operations"]:
        chunk = base64.b64decode(op["data"])
        content.extend(chunk)

    Path(output_path).write_bytes(content)

    return jsonify({"success": True, "message": f"File written to {output_path}"})

@app.route('/analysis/<filename>')
def serve_analysis_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/uploads/<filename>')
def serve_uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)