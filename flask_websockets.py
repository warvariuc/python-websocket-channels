"""
Based on Flask-Sockets (https://github.com/kennethreitz/flask-sockets)
"""
from werkzeug.routing import Map, Rule
from werkzeug.exceptions import HTTPException


class SocketMiddleware(object):

    def __init__(self, wsgi_app):
        self.app = wsgi_app
        self.url_map = Map()
        self.view_functions = {}

    def route(self, rule):

        methods = set(('GET',))  # web-socket endpoints support only GET method

        def decorator(view_func):
            endpoint = view_func.__name__
            _rule = Rule(rule, methods=methods, endpoint=endpoint)
            self.url_map.add(_rule)
            self.view_functions[endpoint] = view_func
            return view_func

        return decorator

    def __call__(self, environ, start_response):
        ws = environ.get('wsgi.websocket')
        if ws is not None:
            url_adapter = self.url_map.bind_to_environ(environ)
            try:
                endpoint, view_args = url_adapter.match()
            except HTTPException as exc:
                ws.close()  # it would ne good to not accept connection at all
                return exc(environ, start_response)

            view_func = self.view_functions[endpoint]
            view_func(ws, **view_args)
        else:
            return self.app(environ, start_response)


def WebSockets(app):
    middleware = SocketMiddleware(app.wsgi_app)
    app.wsgi_app = middleware
    return middleware


from geventwebsocket.gunicorn.workers import GeventWebSocketWorker as worker
