"""
Based on Flask-Sockets (https://github.com/kennethreitz/flask-sockets) and
https://devcenter.heroku.com/articles/python-websockets
"""
from collections import defaultdict
import functools

import gevent
import geventwebsocket.gunicorn.workers

from werkzeug.routing import Map, Rule
from werkzeug.exceptions import HTTPException


class Worker(geventwebsocket.gunicorn.workers.GeventWebSocketWorker):
    """The worker used here.
    TODO: https://github.com/abourget/gevent-socketio/blob/master/socketio/sgunicorn.py
    """


class WebSocketMiddleware(object):

    def __init__(self, wsgi_app, pubsub):
        self.app = wsgi_app
        self.pubsub = pubsub
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
        websocket = environ.get('wsgi.websocket')
        if websocket is not None:
            url_adapter = self.url_map.bind_to_environ(environ)
            try:
                endpoint, view_args = url_adapter.match()
            except HTTPException as exc:
                websocket.close()  # it would be good to not accept connection at all
                return exc(environ, start_response)

            view_func = self.view_functions[endpoint]
            view_func(websocket, **view_args)
        else:
            return self.app(environ, start_response)

    def subscribe_client(self, websocket, channel):
        self.pubsub.subscribe_client(websocket, channel)

    def publish_message(self, message, channel):
        self.pubsub.publish_message(message, channel)


def async(func):
    """Decorator to make functions asynchronous
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return gevent.spawn(func, *args, **kwargs)

    return wrapper


class RedisPubSubBackend(object):
    """Interface for subscribing WebSocket clients to channels and publishing messages for them.
    https://github.com/andymccurdy/redis-py#publish--subscribe
    """
    CHANNEL_PREFIX = 'websocket:'

    def __init__(self, redis_client, app):
        self.redis_client = redis_client
        self.pubsub = redis_client.pubsub(ignore_subscribe_messages=True)
        self.app = app
        self.sockets = defaultdict(set)  # {channel: set([websocket, ...]), ...}

    @async
    def subscribe_client(self, websocket, channel):
        """Asynchronosuly subscribe a client to published messages.

        Args:
            websocket (WebSocket): client websocket
            channel (str): from which channel
        """
        self.sockets[channel].add(websocket)

    @async
    def send_message(self, websocket, message, channel):
        """Asynchronosuly send a message to a websocket client.
        Automatically discard invalid connections.

        Args:
            websocket (WebSocket): client websocket
            message (str): message to send
            channel (str): from which channel
        """
        try:
            websocket.send(message)
        except geventwebsocket.WebSocketError:
            self.sockets[channel].remove(websocket)

    @async
    def publish_message(self, message, channel):
        self.app.logger.info(u'Pusblishing message to channel %s: %s', channel, message)
        self.redis_client.publish(self.CHANNEL_PREFIX + channel, message)

    @async
    def run(self):
        """Listen for new messages in Redis, and send them to clients.
        """
        self.pubsub.psubscribe(self.CHANNEL_PREFIX + '*')  # listen to all channels
        channel_prefix_len = len(self.CHANNEL_PREFIX)
        while True:
            message = self.pubsub.get_message() if self.pubsub.subscribed else None
            if not message:
                gevent.sleep(0.01)  # be nice to the system
                continue
            _message = message['data']
            channel = message['channel'][channel_prefix_len:]
            self.app.logger.info(u'Sending message to clients on channel %s: %s',
                                 channel, _message)
            for websocket in self.sockets[channel]:
                self.send_message(websocket, _message, channel)


def create_websockets_app(app, redis_client):
    pubsub = RedisPubSubBackend(redis_client, app)
    pubsub.run()
    middleware = WebSocketMiddleware(app.wsgi_app, pubsub)
    app.wsgi_app = middleware
    return middleware
