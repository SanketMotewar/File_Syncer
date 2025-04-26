import os
import sys
import time
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

# Add parent directory to Python path
sys.path.append(str(Path(__file__).parent.parent))
from backend.syncer import FileSyncer

# Initialize Flask app with correct paths
from pathlib import Path

# Get the base directory
BASE_DIR = Path(__file__).parent.parent

# Initialize Flask app with absolute paths
app = Flask(__name__,
            template_folder=str(BASE_DIR / 'frontend' / 'templates'),
            static_folder=str(BASE_DIR / 'frontend' / 'static'))# Configuration

app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit
app.secret_key = 'your-secret-key-here'

# Ensure directories exist
Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)

def determine_chunk_size(file_size: int) -> int:
    """Determine optimal chunk size based on file size"""
    if file_size < 1024:
        return 64
    elif file_size < 1024 * 1024:
        return 1024
    elif file_size < 10 * 1024 * 1024:
        return 4096
    return 8192

def prepare_visualization(diff_report: dict) -> list:
    """Prepare data for visual chunk comparison"""
    visualization = []
    
    colors = {
        "added": "#4CAF50",
        "removed": "#F44336",
        "unchanged": "#9E9E9E",
        "modified": "#FFC107"  # Added modified color
    }

    # Process modified chunks first for visual priority
    for mod in diff_report.get("details", {}).get("modified_chunks", []):
        new_chunk = mod.get("new_chunk", {})
        visualization.append({
            "index": new_chunk.get("index", 0),
            "type": "modified",
            "size": new_chunk.get("size", 0),
            "color": colors["modified"],
            "old_offset": mod.get("old_chunk", {}).get("offset", 0),  # Additional context
            "new_offset": new_chunk.get("offset", 0)
        })

    # Process added chunks
    for chunk in diff_report.get("details", {}).get("added_chunks", []):
        visualization.append({
            "index": chunk.get("index", 0),
            "type": "added",
            "size": chunk.get("size", 0),
            "color": colors["added"],
            "offset": chunk.get("offset", 0)
        })

    # Process removed chunks (reference old indexes)
    for chunk in diff_report.get("details", {}).get("removed_chunks", []):
        visualization.append({
            "index": chunk.get("index", 0),
            "type": "removed",
            "size": chunk.get("size", 0),
            "color": colors["removed"],
            "offset": chunk.get("offset", 0)
        })

    # Process unchanged chunks last
    for chunk in diff_report.get("details", {}).get("unchanged_chunks", []):
        visualization.append({
            "index": chunk.get("index", 0),
            "type": "unchanged",
            "size": chunk.get("size", 0),
            "color": colors["unchanged"],
            "offset": chunk.get("offset", 0)
        })

    # Sort by chunk index in new file
    visualization.sort(key=lambda x: x["index"])
    
    return visualization

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/compare', methods=['POST'])
def compare_files():
    try:
        if 'old_file' not in request.files or 'new_file' not in request.files:
            return jsonify({"status": "error", "message": "Both files are required"}), 400

        old_file = request.files['old_file']
        new_file = request.files['new_file']

        if not old_file.filename or not new_file.filename:
            return jsonify({"status": "error", "message": "No files selected"}), 400

        # Secure filenames and save files
        old_filename = secure_filename(old_file.filename)
        new_filename = secure_filename(new_file.filename)
        upload_dir = Path(app.config['UPLOAD_FOLDER'])
        
        old_path = upload_dir / old_filename
        new_path = upload_dir / new_filename
        
        old_file.save(str(old_path))
        new_file.save(str(new_path))

        # Determine chunk size
        file_size = max(old_path.stat().st_size, new_path.stat().st_size)
        chunk_size = determine_chunk_size(file_size)
        
        # Analyze files
        syncer = FileSyncer(chunk_size=chunk_size)
        start_time = time.time()
        analysis = syncer.analyze_files(str(old_path), str(new_path))

        if not analysis.get('success', False):
            return jsonify({"status": "error", "message": analysis.get('error', 'Unknown error')}), 400

        # Prepare response
        sync_plan = syncer.generate_sync_plan(analysis)
        visualization = prepare_visualization(analysis.get('data', {}))

        return jsonify({
            "status": "success",
            "diff_report": analysis.get('data', {}),
            "sync_plan": sync_plan,
            "visualization": visualization,
            "analysis_time": time.time() - start_time,
            "old_filename": old_filename,
            "new_filename": new_filename
        })

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/uploads/<filename>')
def serve_uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)