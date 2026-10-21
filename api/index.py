import sys
import os

# Add root project directory to sys.path so 'app' package can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

app = create_app()

class VercelPathMiddleware:
    """
    WSGI Middleware to normalize request paths on Vercel.
    Ensures that paths rewritten to /api/index or forwarded with X-Matched-Path
    are accurately mapped to Flask's root and blueprint routes.
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        # 1. Check for original matched path forwarded by Vercel edge
        matched_path = environ.get('HTTP_X_MATCHED_PATH')
        if matched_path and not matched_path.startswith('/api/'):
            environ['PATH_INFO'] = matched_path
        else:
            # 2. Normalize PATH_INFO if Vercel prepends /api/index or /api
            path = environ.get('PATH_INFO', '')
            if path in ('/api/index', '/api/index/', '/api', '/api/'):
                environ['PATH_INFO'] = '/'
            elif path.startswith('/api/index/'):
                environ['PATH_INFO'] = path[len('/api/index'):]
            elif path.startswith('/api/'):
                environ['PATH_INFO'] = path[len('/api'):]

        return self.wsgi_app(environ, start_response)

app.wsgi_app = VercelPathMiddleware(app.wsgi_app)

if __name__ == "__main__":
    app.run()
