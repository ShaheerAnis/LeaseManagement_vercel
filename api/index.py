import sys
import os

# Add root project directory to sys.path so 'app' package can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

# Vercel looks for the WSGI/ASGI 'app' object in api/index.py
app = create_app()

if __name__ == "__main__":
    app.run()
