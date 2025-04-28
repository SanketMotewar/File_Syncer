import os
import sys
import time
import base64
import shutil
import logging
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

def apply_sync_plan(old_file_path, sync_plan, output_file_path):
    """Apply the sync plan to create a synchronized file"""
    with open(old_file_path, 'rb') as f:
        old_data = f.read()

    new_data = bytearray()
    for operation in sync_plan:
        op_type = operation['operation']
        offset = operation['offset']
        size = operation['size']

        if op_type == 'ADD':
            chunk_data = base64.b64decode(operation['data'])
            new_data.extend(chunk_data)
        elif op_type == 'REMOVE':
            continue
        elif op_type == 'UNCHANGED':
            new_data.extend(old_data[offset:offset + size])

    with open(output_file_path, 'wb') as f:
        f.write(new_data)

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
        if not res.get("success",False):
            return jsonify(status="error", message=res.get("error","Analysis failed")), 400

        plan = syncer.generate_sync_plan(res)
        viz  = prepare_visualization(res["data"])

        # write analysis file
        try:
            txt = generate_human_readable_analysis(old_fn, new_fn, res["data"], plan)
            ts = int(time.time())
            af = UP/f"analysis_{ts}.txt"
            af.write_text(txt, encoding="utf-8")
            analysis_file = af.name
        except Exception:
            logging.exception("Failed to write analysis file")
            analysis_file = None

        return jsonify({
            "status": "success",
            "diff_report": res["data"],
            "sync_plan": plan,
            "visualization": viz,
            "analysis_time": time.time() - start,
            "old_filename": old_fn,
            "new_filename": new_fn,
            "analysis_file": analysis_file
        })

    except Exception:
        logging.exception("Error in /compare")
        return jsonify(status="error", message="Internal server error"), 500

# 🔥 Helper function to generate human-readable analysis
def generate_human_readable_analysis(old_fn, new_fn, diff_data, sync_plan):
    """
    Build a text report that never crashes even if some keys are missing.
    Uses op['new_data'] for MODIFY and op['data'] for ADD.
    """
    out = []
    out.append(f"Old File: {old_fn}")
    out.append(f"New File: {new_fn}")
    out.append("="*50)

    # summary
    sumry = diff_data.get("summary",{})
    out.append("\n=== Summary ===")
    out.append(f"Total   : {sumry.get('total_chunks',0)}")
    out.append(f"Unchanged: {sumry.get('unchanged',0)}")
    out.append(f"Added   : {sumry.get('added',0)} ({sumry.get('bytes_added',0)} bytes)")
    out.append(f"Removed : {sumry.get('removed',0)} ({sumry.get('bytes_removed',0)} bytes)")
    out.append(f"Modified: {sumry.get('modified',0)}")
    out.append(f"Change% : {sumry.get('changed_percent',0):.1f}%")

    # old chunks
    out.append("\n=== Old File Chunks (kept or removed) ===")
    for c in diff_data.get("details",{}).get("removed_chunks",[])+diff_data.get("details",{}).get("unchanged_chunks",[]):
        content = ""
        try:
            content = base64.b64decode(c.get("data","")).decode("utf-8",errors="replace")
        except:
            pass
        out.append(f"Chunk {c['index']}: Offset {c['offset']} Size {c['size']}")
        out.append("  " + content.replace("\n","\n  "))

    # new chunks
    out.append("\n=== New File Chunks (added or kept) ===")
    for c in diff_data.get("details",{}).get("added_chunks",[])+diff_data.get("details",{}).get("unchanged_chunks",[]):
        content = ""
        try:
            content = base64.b64decode(c.get("data","")).decode("utf-8",errors="replace")
        except:
            pass
        out.append(f"Chunk {c['index']}: Offset {c['offset']} Size {c['size']}")
        out.append("  " + content.replace("\n","\n  "))

    # sync plan
    out.append("\n=== Synchronization Plan ===")
    out.append(f"Total Operations: {len(sync_plan.get('operations',[]))}")
    out.append(f"Total Bytes: {sync_plan.get('total_bytes',0)}")
    out.append(f"Efficiency: {sync_plan.get('efficiency',0)}%")
    for i,op in enumerate(sync_plan.get("operations",[]),1):
        out.append(f"\nOperation {i}: {op.get('type','?')}")
        out.append(f"  Offset: {op.get('offset','?')}  Size: {op.get('size','?')}")
        if op.get("type")=="ADD":
            data_b64 = op.get("data","")
            try:
                txt = base64.b64decode(data_b64).decode("utf-8",errors="replace")
                out.append("  Added Content:\n    " + txt.replace("\n","\n    "))
            except:
                pass
        if op.get("type")=="MODIFY":
            nd = op.get("new_data","")
            try:
                txt = base64.b64decode(nd).decode("utf-8",errors="replace")
                out.append("  New Content:\n    " + txt.replace("\n","\n    "))
            except:
                pass
        if op.get("type")=="REMOVE":
            out.append("  Action: Remove bytes")

    return "\n".join(out)

@app.route('/analysis/<filename>')
def serve_analysis_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/synchronize', methods=['POST'])
def synchronize_files():
    try:
        data = request.get_json(force=True)
        ops = data.get("operations",[])
        old_fn = data.get("old_file")
        if not old_fn or not ops:
            return jsonify(status="error", message="Missing data"),400

        UP = Path(app.config['UPLOAD_FOLDER'])
        old_path = UP/old_fn
        if not old_path.exists():
            return jsonify(status="error", message="Old file not found"),404

        dst = UP/f"synced_{old_fn}"
        shutil.copyfile(old_path, dst)
        logging.debug(f"Copied to {dst}")

        content = bytearray(dst.read_bytes())
        for op in ops:
            t = op.get("type")
            off = op.get("offset",0)
            sz  = op.get("size",0)
            if t=="ADD":
                d = base64.b64decode(op.get("data",""))
                content[off:off] = d
            elif t=="REMOVE":
                del content[off:off+sz]
            elif t=="MODIFY":
                nd = base64.b64decode(op.get("new_data",""))
                content[off:off+sz] = nd
        dst.write_bytes(content)

        return jsonify(status="success", message="Synchronized", output_file=dst.name)

    except Exception:
        logging.exception("Error in /synchronize")
        return jsonify(status="error", message="Internal server error"), 500

@app.route('/uploads/<filename>')
def serve_uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)