flask_amc_analyzer/
│
├── app.py                     # Main application file
├── config.py                  # Configuration settings for the Flask app
├── requirements.txt           # Python package dependencies
│
├── core/                      # Core functionality of the application
│   ├── __init__.py           # Initialize the core package
│   ├── database.py            # Database handling functions
│   ├── file_processor.py      # File processing functions
│   ├── deepseek_client.py     # DeepSeek client interactions
│   ├── voice_handler.py       # Voice handling functions
│   └── amazon_client_amc.py   # Functions for generating AMC reports
│
├── templates/                 # HTML templates for rendering
│   ├── base.html              # Base template for other pages
│   └── index.html             # Index page template
│
├── static/                    # Static files (CSS, JS, images)
│   ├── css/                   # CSS files
│   │   └── styles.css         # Main stylesheet
│   └── js/                    # JavaScript files
│       └── scripts.js         # Main JavaScript file
│
└── instance/                  # Instance folder for configuration and database
    └── config.py              # Instance-specific configuration