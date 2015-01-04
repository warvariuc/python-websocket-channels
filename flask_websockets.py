"""
Based on Flask-Sockets (https://github.com/kennethreitz/flask-sockets) and
https://devcenter.heroku.com/articles/python-websockets
"""
from collections import defaultdict
import functools

import redis
import gevent
import geventwebsocket.gunicorn.workers

from werkzeug.routing import Map, Rule
from werkzeug.exceptions import HTTPException


class Worker(geventwebsocket.gunicorn.workers.GeventWebSocketWorker):
    """The worker used here.
    TODO: https://github.com/abourget/gevent-socketio/blob/master/socketio/sgunicorn.py
    """


def async(func):
    """Decorator to make functions asynchronous
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return gevent.spawn(func, *args, **kwargs)

    return wrapper


class WebSocketMiddleware(object):
    """
    """
    REDIS_CHANNEL_PREFIX = 'websocket:'

    def __init__(self, app, redis_url):
        self.app = app
        self.url_map = Map()
        self.view_functions = {}
        self.redis_client = redis.from_url(redis_url)
        self.pubsub = self.redis_client.pubsub(ignore_subscribe_messages=True)
        self.sockets = defaultdict(set)  # {channel: set([websocket, ...]), ...}
        self._listen()

    def route(self, rule):

        def decorator(view_func):
            endpoint = view_func.__name__
            _rule = Rule(rule, endpoint=endpoint)
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

    @async
    def register_websocket(self, websocket, channel):
        """Asynchronously register a web-socket so it can be sent published messages.

        Args:
            websocket (WebSocket): websocket
            channel (str): on which channel
        """
        self.sockets[channel].add(websocket)

    @async
    def publish_message(self, message, channel):
        """Asynchronously PUBLISH a message to the given Redis channel. SUBSCRIBEd Redis clients
        will be notified about it.

        Args:
            message (str): message to publish
            channel (str): on which channel
        """
        self.app.logger.info(u'Pusblishing message to channel %s: %s', channel, message)
        self.redis_client.publish(self.REDIS_CHANNEL_PREFIX + channel, message)

    @async
    def _listen(self):
        """Listen in a thread for new messages in Redis, and send them to registered web-sockets.
        See: https://github.com/andymccurdy/redis-py#publish--subscribe
        """
        self.pubsub.psubscribe(self.REDIS_CHANNEL_PREFIX + '*')  # listen to all channels
        channel_prefix_len = len(self.REDIS_CHANNEL_PREFIX)
        while True:
            message = self.pubsub.get_message() if self.pubsub.subscribed else None
            if not message:
                gevent.sleep(0.05)  # be nice to the system
                continue
            _message = message['data']
            channel = message['channel'][channel_prefix_len:]
            self.app.logger.info(u'Sending message to clients on channel %s: %s',
                                 channel, _message)
            for websocket in self.sockets[channel]:
                self._send_websocket_message(websocket, _message, channel)

    @async
    def _send_websocket_message(self, websocket, message, channel):
        """Asynchronously send a message to the given websocket.
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
