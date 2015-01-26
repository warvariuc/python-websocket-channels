import gevent.monkey
gevent.monkey.patch_all()

import functools
import argparse
import logging
import os

from ws4py.server.geventserver import WebSocketWSGIApplication, WSGIServer, WebSocketWSGIHandler
import ws4py.websocket

import gevent.queue
import redis
from werkzeug.routing import Map, Rule
from werkzeug.wrappers import BaseResponse as Response
from werkzeug.exceptions import HTTPException
from werkzeug.utils import cached_property
from jinja2 import Environment, FileSystemLoader


logger = logging.getLogger(__name__)


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
        self.name = name  # channel name
        self.websockets = set()  # websockets on this channel
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


class WebSocket(ws4py.websocket.WebSocket):

    def __init__(self, sock, protocols=None, extensions=None, environ=None, heartbeat_freq=None):
        super(WebSocket, self).__init__(sock, protocols, extensions, environ, heartbeat_freq)
        self.app = self.environ['.app']
        self.channel = self.environ['.channel']

    def opened(self):
        self.app.register_websocket(self, self.channel)

    def received_message(self, message):
        self.app.on_message_received(message, self.channel)

    # TODO: call self.app.on_websocket_closed to expunge websocket from channel_sockets
    # def closed(self, code, reason="A client left the room without a proper explanation."):
    #     app = self.environ.pop('.app')
    #     if self in app.clients:
    #         app.clients.remove(self)
    #         for client in app.clients:
    #             try:
    #                 client.send(reason)
    #             except:
    #                 pass


BASE_DIR = os.path.abspath(os.path.dirname(__name__) + '/..')
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')


class WebSocketChannelApp(WebSocketWSGIApplication):

    REDIS_CHANNEL_PREFIX = 'websocket:'

    def __init__(self, redis_url, protocols=None, extensions=None, handler_cls=WebSocket):
        super(WebSocketChannelApp, self).__init__(protocols, extensions, handler_cls)
        self.redis_client = redis.from_url(redis_url)
        self.channel_sockets = ChannelSockets('')
        self.jinja_env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)
        self.published_message_queue = gevent.queue.Queue()
        self.consume_published_messages()
        self.pubsub = self.redis_client.pubsub(ignore_subscribe_messages=True)
        self.listen_redis()

    @async
    def consume_published_messages(self):
        """Get messages to publish from the queue and PUBLISH them to Redis and one connection.
        """
        from gevent.queue import Timeout, Empty
        redis_pipeline = self.redis_client.pipeline(transaction=False)
        while True:
            try:
                while True:
                    message, channel = self.published_message_queue.get(timeout=0.01)
                    logger.info(u'Publishing message on channel `%s`: %s', channel, message)
                    redis_pipeline.publish(self.REDIS_CHANNEL_PREFIX + channel, message)
            except (Timeout, Empty):
                redis_pipeline.execute()

    @cached_property
    def url_map(self):
        return Map([
            Rule('/', endpoint='home'),
            Rule('/channel/<path:channel>', endpoint='channel'),
            Rule('/ws/<path:channel>', endpoint='ws')
        ])

    def view_home(self, environ):
        return self.render_template('home.html')

    def view_channel(self, environ, channel):
        return self.render_template('channel.html', channel=channel)

    def view_ws(self, environ, channel):
        environ['.app'] = self
        environ['.channel'] = channel
        return super(WebSocketChannelApp, self).__call__

    def render_template(self, template_name, **context):
        template = self.jinja_env.get_template(template_name)
        return Response(template.render(context), mimetype='text/html')

    def __call__(self, environ, start_response):
        environ['ws4py.websocket'] = None  # to be removed -- in the newer ws4py it's not needed
        adapter = self.url_map.bind_to_environ(environ)
        try:
            endpoint, view_args = adapter.match()
            view = getattr(self, 'view_' + endpoint)
        except HTTPException as exc:
            view = exc
            view_args = {}

        return view(environ, **view_args)(environ, start_response)

    def register_websocket(self, websocket, channel):
        """Callback to register a websocket so it can be sent published messages.
        """
        sockets = self.channel_sockets
        for channel in channel.split('/'):
            sockets = sockets[channel]
        sockets.websockets.add(websocket)

    def on_message_received(self, message, channel):
        """Callback called when a new message from a client via websocket arrives.
        The default implementation publishes the message. You can subclass this to apply custom
        logic (e.g filtering).

        Args:
            message (ws4py.messaging.Message): the received message
            channel (str): on which channel
        """
        self.publish_message(message.data, channel)

    def publish_message(self, message, channel):
        """Asynchronously PUBLISH a message to the given Redis channel. SUBSCRIBEd Redis clients
        will be notified about it.

        Args:
            message (str): message to publish
            channel (str): on which channel
        """
        self.published_message_queue.put((message, channel))

    @async
    def listen_redis(self):
        """Listen in a thread for new messages in Redis, and send them to registered web-sockets.
        See: https://github.com/andymccurdy/redis-py#publish--subscribe
        """
        channel_prefix_len = len(self.REDIS_CHANNEL_PREFIX)
        self.pubsub.psubscribe(self.REDIS_CHANNEL_PREFIX + '*')  # listen to all channels

        for message in self.pubsub.listen():
            channel = message['channel'][channel_prefix_len:]
            # logger.info(u'Received a message on channel `%s`: %s', channel, message['data'])
            self.send_message(channel, message['data'])

    def send_message(self, channel, message):
        """Asynchronously send a message to websockets handled by this process on the given 
        channel.
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
        """Send the given meesage to websockets only of the given channel.
        """
        websockets = channel_sockets.websockets
        for websocket in tuple(websockets):  # changes during iteration
            if websocket.terminated:
                websockets.remove(websocket)
            else:
                websocket.send(message)

    def _send_message_subchannels(self, message, channel_sockets):
        """Send the given meesage to weboskets only of subchannels of the given channel.
        """
        for channel_sockets in channel_sockets:
            self._send_message_channel(message, channel_sockets)
            self._send_message_subchannels(message, channel_sockets)


try:
    from gunicorn.workers.ggevent import GeventPyWSGIWorker, PyWSGIHandler

    class WSGIHandler(PyWSGIHandler, WebSocketWSGIHandler):
        pass

    class Worker(GeventPyWSGIWorker):
        """Worker for Gunicorn.
        """
        server_class = WSGIServer
        wsgi_handler = WSGIHandler
except ImportError:
    pass


REDIS_URL = 'redis://127.0.0.1:6379/0'
application = WebSocketChannelApp(redis_url=REDIS_URL)


if __name__ == '__main__':

    logger = ws4py.configure_logger(level='INFO')

    parser = argparse.ArgumentParser(description='Echo gevent Server')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=9000, type=int)
    args = parser.parse_args()

    server = WSGIServer((args.host, args.port), application)
    server.serve_forever()
