flask_amc_analyzer/
│
├── app.py                     # Main application file
├── requirements.txt           # Python package dependencies
│
├── core/                      # Core functionality
│   ├── __init__.py           # Initialize the core module
│   ├── database.py           # Database handling
│   ├── file_processor.py      # File processing logic
│   ├── deepseek_client.py     # DeepSeek client logic
│   ├── voice_handler.py       # Voice handling logic
│   └── amazon_client_amc.py   # Amazon AMC report generation logic
│
├── templates/                 # HTML templates
│   ├── base.html              # Base template
│   └── index.html             # Index page
│
├── static/                    # Static files (CSS, JS, images)
│   ├── css/
│   │   └── styles.css         # CSS styles
│   ├── js/
│   │   └── scripts.js         # JavaScript files
│   └── images/                # Image files
│
└── session_id.txt             # Session ID file (if needed)