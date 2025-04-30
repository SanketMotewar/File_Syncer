
```markdown
# File Chunk Syncer 🚀

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.0%2B-lightgrey)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

## Table of Contents 📑
1. [Key Features](#key-features-)
2. [Installation](#installation-)
3. [Usage](#usage-)
4. [API Endpoints](#api-endpoints-)
5. [Project Structure](#project-structure-)
6. [Key Algorithms](#key-algorithms-)
7. [Contributing](#contributing-)
8. [License](#license-)
9. [Acknowledgments](#acknowledgments-)

An intelligent file synchronization system using content-defined chunking and SHA-256 hashing for efficient differential file transfers.

**Now working 100%** with critical fixes for:
- Proper synchronized file naming (`synced_old_version.txt`)
- Accurate total chunk calculations
- Reliable sync operations

## Key Features ✨ <a name="key-features-"></a>
- 📂 Content-defined chunking with rolling hash algorithm
- 🔍 SHA-256 hash-based file comparison
- 📈 Visual chunk difference analysis
- ⚡ Efficient sync plan generation
- 🌐 Web-based interface with real-time visualization
- 📊 Detailed change statistics and metrics
- 🔄 Smart similarity detection for modified chunks

## Installation 🛠️ <a name="installation-"></a>
```bash
git clone https://github.com/yourusername/file-chunk-syncer.git
cd file-chunk-syncer

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate    # Windows

# Install dependencies
pip install flask werkzeug
```

## Usage 🖥️ <a name="usage-"></a>
Start the development server:
```bash
python app.py
```
Access the web interface at `http://localhost:5000`

### Upload files:
1. Select "Original File" (old version)
2. Select "Modified File" (new version)
3. Click "Compare Files"

### View results:
- Interactive chunk visualization
- Detailed change statistics
- Sync operation list
- Efficiency metrics

### Execute synchronization:
1. Click "Synchronize Files"
2. Get `synced_old_version.txt` with minimal transfers

## API Endpoints 🔌 <a name="api-endpoints-"></a>
| Endpoint        | Method | Description                     |
|-----------------|--------|---------------------------------|
| `/compare`      | POST   | Compare two files               |
| `/synchronize`  | POST   | Execute synchronization plan    |
| `/uploads/*`    | GET    | Access uploaded files           |
| `/analysis/*`   | GET    | Download text analysis reports  |

## Project Structure 🗂️ <a name="project-structure-"></a>
```
├── backend/
│   ├── chunker.py    # Content-defined chunking logic
│   ├── differ.py     # File comparison engine
│   ├── hasher.py     # SHA-256 chunk hashing
│   └── syncer.py     # Sync plan generator
├── frontend/
│   ├── static/       # CSS/JS assets
│   └── templates/index.html    # HTML templates
├── app.py            # Flask application
└── requirements.txt  # Dependencies
```

## Key Algorithms 🔬 <a name="key-algorithms-"></a>
### Rolling Hash Chunking:
- Uses polynomial rolling hash with windowing
- Automatic chunk size adjustment
- Newline-aware boundary detection

### Similarity Detection:
- Byte-level content matching
- Configurable similarity threshold (70% default)
- Base64-optimized comparisons

### Sync Optimization:
- Minimal data transfer planning
- Efficiency percentage calculation
- Bandwidth estimation (10MB/s baseline)

## Contributing 🤝 <a name="contributing-"></a>
1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## License 📄 <a name="license-"></a>
This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments 🎓 <a name="acknowledgments-"></a>
- Flask framework for web interface
- Content-Defined Chunking (CDC) concepts
- Rolling hash algorithm inspiration
- Modern web visualization techniques

> **Note**: This is a development version - for production use, consider:
> - Adding authentication
> - Implementing rate limiting
> - Using proper WSGI server (Gunicorn/uWSGI)
> - Setting up HTTPS
```
