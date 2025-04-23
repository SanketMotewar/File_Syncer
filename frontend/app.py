from flask import Flask, render_template, request, jsonify, send_from_directory
import os
from werkzeug.utils import secure_filename
from backend.syncer import FileSyncer
import time
from pathlib import Path
from typing import Dict, List

# Initialize Flask app
app = Flask(__name__, 
            template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
            static_folder=os.path.join(os.path.dirname(__file__), 'static'))

# Configuration
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit
app.secret_key = 'your-secret-key-here'

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def determine_chunk_size(file_size: int) -> int:
    """Determine optimal chunk size based on file size"""
    if file_size < 1024:  # < 1KB
        return 64
    elif file_size < 1024 * 1024:  # < 1MB
        return 1024
    elif file_size < 10 * 1024 * 1024:  # < 10MB
        return 4096
    else:  # >= 10MB
        return 8192

def prepare_visualization(diff_report: Dict) -> List[Dict]:
    """Prepare data for visual chunk comparison"""
    visualization = []
    
    # Process added chunks
    for chunk in diff_report["details"].get("added_chunks", []):
        visualization.append({
            "index": chunk.get("index", 0),
            "type": "added",
            "size": chunk["size"],
            "color": "#4CAF50"  # Green
        })
    
    # Process removed chunks
    for chunk in diff_report["details"].get("removed_chunks", []):
        visualization.append({
            "index": chunk.get("index", 0),
            "type": "removed",
            "size": chunk["size"],
            "color": "#F44336"  # Red
        })
    
    # Process unchanged chunks
    for chunk in diff_report["details"].get("unchanged_chunks", []):
        visualization.append({
            "index": chunk.get("index", 0),
            "type": "unchanged",
            "size": chunk["size"],
            "color": "#9E9E9E"  # Gray
        })
    
    # Sort by index
    visualization.sort(key=lambda x: x["index"])
    
    return visualization

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/compare', methods=['POST'])
def compare_files():
    try:
        # Validate request
        if 'old_file' not in request.files or 'new_file' not in request.files:
            return jsonify({"status": "error", "message": "Both files are required"}), 400
        
        old_file = request.files['old_file']
        new_file = request.files['new_file']
        
        if old_file.filename == '' or new_file.filename == '':
            return jsonify({"status": "error", "message": "No files selected"}), 400
        
        # Secure filenames and save files
        old_filename = secure_filename(old_file.filename)
        new_filename = secure_filename(new_file.filename)
        
        old_path = os.path.join(app.config['UPLOAD_FOLDER'], old_filename)
        new_path = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
        
        old_file.save(old_path)
        new_file.save(new_path)
        
        # Analyze files with dynamic chunk sizing
        file_size = max(os.path.getsize(old_path), os.path.getsize(new_path))
        chunk_size = determine_chunk_size(file_size)
        
        syncer = FileSyncer(chunk_size=chunk_size)
        start_time = time.time()
        analysis = syncer.analyze_files(old_path, new_path)
        
        if not analysis['success']:
            return jsonify({"status": "error", "message": analysis['error']}), 400
        
        # Generate sync plan and visualization
        sync_plan = syncer.generate_sync_plan(analysis)
        visualization = prepare_visualization(analysis['data'])
        
        return jsonify({
            "status": "success",
            "diff_report": analysis['data'],
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
    app.run(debug=True, port=5000)