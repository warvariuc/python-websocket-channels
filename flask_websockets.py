"""
Based on Flask-Sockets (https://github.com/kennethreitz/flask-sockets) and
https://devcenter.heroku.com/articles/python-websockets
"""
from collections import defaultdict
import functools

import redis
import gevent
import geventwebsocket.gunicorn.workers


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
        self.redis_client = redis.from_url(redis_url)
        self.pubsub = self.redis_client.pubsub(ignore_subscribe_messages=True)
        self.sockets = defaultdict(set)  # {channel: set([websocket, ...]), ...}
        self._listen()

    def __call__(self, environ, start_response):
        websocket = environ.get('wsgi.websocket')
        if websocket is not None:
            channel = environ['PATH_INFO'].lstrip('/')
            self._handle_websocket_connection(websocket, channel)
        else:  # call the wrapped app
            return self.app(environ, start_response)

    def _register_websocket(self, websocket, channel):
        """Register a web-socket so it can be sent published messages.
        """
        self.sockets[channel].add(websocket)

    def _handle_websocket_connection(self, websocket, channel):
        """Receive messages the web-socket.
        """
        self._register_websocket(websocket, channel)
        while not websocket.closed:
            gevent.sleep(0.05)  # switch to send messages
            message = websocket.receive()
            if message:
                self.on_message(message, channel)

    def on_message(self, message, channel):
        """Hook called when a new message from a client via websocket arrives.
        The default implementation publishes the message. You can subclass this to apply custom
        logic (e.g filtering).

        Args:
            message (str): message to publish
            channel (str): on which channel
        """
        self.publish_message(message, channel)

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
            channel = message['channel'][channel_prefix_len:]
            self._send_message(channel, message['data'])

    @async
    def _send_message(self, channel, message):
        """Asynchronously send a message to websockets handled by this worker on the given channel.
        """
        self.app.logger.info(u'Sending message to clients on channel %s: %s', channel, message)
        websockets = self.sockets[channel]
        for websocket in tuple(websockets):  # changes during iteration
            try:
                websocket.send(message)
            except geventwebsocket.WebSocketError:
                # discard invalid connection
                websockets.remove(websocket)
