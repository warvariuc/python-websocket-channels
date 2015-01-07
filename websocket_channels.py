"""
Based on Flask-Sockets (https://github.com/kennethreitz/flask-sockets) and
https://devcenter.heroku.com/articles/python-websockets
"""
import functools
import logging

import redis
import gevent
import geventwebsocket.gunicorn.workers


logger = logging.getLogger(__name__)


class Worker(geventwebsocket.gunicorn.workers.GeventWebSocketWorker):
    """The worker used here.
    """
    # TODO: It would be nice to hook on WebSocket connection handshake to be able to reject
    # TODO: undesired connections
    # TODO: https://github.com/abourget/gevent-socketio/blob/master/socketio/sgunicorn.py


def async(func):
    """Decorator to make a function to be executed asynchronously using a Greenlet.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return gevent.spawn(func, *args, **kwargs)

    return wrapper


class ChannelSockets(object):
    """Channels and WebSockets registered on them.
    """
    def __init__(self, name):
        self.name = name
        self.websockets = set()
        self._subchannels = {}

    def __getitem__(self, name):
        """Get a sub-channel.
        """
        channel = self._subchannels.get(name)
        if channel is None:
            channel = self.__class__(self.name + '/' + name)
            self._subchannels[name] = channel
        return channel

    def __iter__(self):
        return self._subchannels.itervalues()


class WebSocketChannelMiddleware(object):
    """WSGI middleware around a WSGI application which expects `wsgi.websocket` request
    environment value provided by a Gunicorn worker and handles that websocket.
    """
    REDIS_CHANNEL_PREFIX = 'websocket:'

    def __init__(self, wsgi_app, redis_url):
        self.wsgi_app = wsgi_app
        self.redis_client = redis.from_url(redis_url)
        self.pubsub = self.redis_client.pubsub(ignore_subscribe_messages=True)
        self.channel_sockets = ChannelSockets('')
        self._listen()

    def __call__(self, environ, start_response):
        websocket = environ.get('wsgi.websocket')
        if websocket is not None:
            channel = environ['PATH_INFO'].strip('/')
            self._handle_websocket_connection(websocket, channel)
        else:  # call the wrapped app
            return self.wsgi_app(environ, start_response)

    def _handle_websocket_connection(self, websocket, channel):
        """Receive messages a websocket.
        """
        self._register_websocket(websocket, channel)
        while not websocket.closed:
            gevent.sleep(0.05)  # switch to send messages
            message = websocket.receive()
            if message:
                self.on_message(message, channel)

    def _register_websocket(self, websocket, channel):
        """Register a websocket so it can be sent published messages.
        """
        sockets = self.channel_sockets
        for channel in channel.split('/'):
            sockets = sockets[channel]
        sockets.websockets.add(websocket)

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
        logger.info(u'Pusblishing message on channel `%s`: %s', channel, message)
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
            logger.debug(u'Received a message on channel `%s`: %s', channel, message)
            self._send_message(channel, message['data'])

    @async
    def _send_message(self, channel, message):
        """Asynchronously send a message to websockets handled by this worker on the given channel.
        """
        only_subchannels = channel.endswith('/')
        if only_subchannels:
            logger.info(u'Sending message to clients on sub-channels of `%s`: %s',
                        channel, message)
        else:
            logger.info(u'Sending message to clients on channel `%s`: %s', channel, message)
        channel_sockets = self.channel_sockets
        for channel in channel.split('/'):
            if channel:
                channel_sockets = channel_sockets[channel]

        if only_subchannels:
            self._send_message_subchannels(message, channel_sockets)
        else:
            self._send_message_channel(message, channel_sockets)

    def _send_message_channel(self, message, channel_sockets):
        """Send the given meesage only to websockets of the given channel.
        """
        websockets = channel_sockets.websockets
        for websocket in tuple(websockets):  # changes during iteration
            try:
                websocket.send(message)
            except geventwebsocket.WebSocketError:
                # discard invalid connection
                websockets.remove(websocket)

    def _send_message_subchannels(self, message, channel_sockets):
        """Send the given meesage to weboskets only of subchannels of the given channel.
        """
        for channel_sockets in channel_sockets:
            self._send_message_channel(message, channel_sockets)
            self._send_message_subchannels(message, channel_sockets)
