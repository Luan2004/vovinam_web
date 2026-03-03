# manager.py
from urls import routes
import traceback

def app2(environ, start_response):
    path = environ.get('PATH_INFO', '/') or '/'
    if path.endswith('/') and path != '/':
        path = path.rstrip('/')

    handler = routes.get(path)

    if not handler:
        start_response(
            '404 Not Found',
            [('Content-Type', 'text/plain; charset=utf-8')]
        )
        return [b'404 Page Not Found']

    try:
        body, status, headers = handler(environ)

        start_response(status, headers)
        return [body]

    except Exception:
        err = traceback.format_exc()
        start_response(
            '500 Internal Server Error',
            [('Content-Type', 'text/plain; charset=utf-8')]
        )
        return [err.encode()]
