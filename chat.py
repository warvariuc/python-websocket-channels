"""
This simple application uses WebSockets to run a primitive chat server.
gunicorn chat:app --config=gunicorn_settings.py
https://devcenter.heroku.com/articles/python-websockets
https://github.com/andymccurdy/redis-py#publish--subscribe
https://github.com/benoitc/gunicorn/blob/master/examples/example_config.py
"""
from collections import defaultdict

import redis
import gevent
import geventwebsocket
import flask

import flask_websockets


REDIS_URL = 'redis://127.0.0.1:6379/0'

app = flask.Flask(__name__)

websockets = flask_websockets.WebSockets(app)
redis_client = redis.from_url(REDIS_URL)


class ChatBackend(object):
    """Interface for registering and updating WebSocket clients.
    """
    def __init__(self):
        self.sockets = defaultdict(set)  # {channel: set([web-sockets]), ...}
        self.pubsub = redis_client.pubsub()
        self.pubsub.psubscribe('*')

    def add_client(self, ws, channel):
        """Register a WebSocket connection for Redis updates.
        """
        self.pubsub.subscribe(channel)
        self.sockets[channel].add(ws)

    def send(self, ws, channel, data):
        """Send given data to the registered client. Automatically discards invalid connections.
        """
        app.logger.info(u'Sending message to a client from channel "%s": %s' % (channel, data))
        try:
            ws.send(data)
        except geventwebsocket.WebSocketError:
            self.sockets[channel].remove(ws)

    def _run(self):
        """Listens for new messages in Redis, and sends them to clients.
        """
        while True:
            message = self.pubsub.get_message()
            if message:
                if message['type'] == 'message':
                    channel = message['channel']
                    for ws in self.sockets[channel]:
                        gevent.spawn(self.send, ws, channel, message.get('data'))
            else:
                gevent.sleep(0.01)  # be nice to the system

    def run(self):
        """Maintains Redis subscription in the background.
        """
        gevent.spawn(self._run)


chats = ChatBackend()
chats.run()


@app.route('/')
def hello():
    return flask.render_template('index.html')


@app.route('/<channel>')
def chat(channel):
    return flask.render_template('chat.html', channel=channel)


@websockets.route('/<channel>')
def channel(ws, channel):
    """Accept web-socket connection to receive chat messages the client wants to send to others.
    The message is PUBLISHed to Redis so the SUBSCIRBEd clients can receive it.
    """
    chats.add_client(ws, channel)
    while not ws.closed:
        # Sleep to prevent *constant* context-switches.
        gevent.sleep(0.1)

        message = ws.receive()
        if message:
            app.logger.info(u'Inserting message: {}'.format(message))
            redis_client.publish(channel, message)
