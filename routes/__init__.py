flask_amc_analyzer/
│
├── app.py                     # Main application file
├── config.py                  # Configuration settings for the Flask app
├── requirements.txt           # Python dependencies
│
├── core/                      # Core functionality of the application
│   ├── __init__.py            # Initialize the core package
│   ├── database.py            # Database interaction logic
│   ├── file_processor.py       # File processing logic
│   ├── deepseek_client.py      # DeepSeek client logic
│   ├── voice_handler.py        # Voice handling logic
│   └── amazon_client_amc.py    # Amazon AMC report generation logic
│
├── templates/                 # HTML templates
│   ├── base.html              # Base template for other pages
│   └── index.html             # Index page template
│
├── static/                    # Static files (CSS, JS, images)
│   ├── css/
│   │   └── styles.css         # CSS styles
│   └── js/
│       └── scripts.js         # JavaScript files
│
└── session_id.txt             # Session ID file (if needed)