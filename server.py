# coding: utf-8

"""
Chat Server
===========
This simple application uses WebSockets to run a primitive chat server.
"""

import os
import logging

import redis
import gevent

from flask import Flask, request
from flask_sockets2 import Sockets


REDIS_URL = os.environ['REDISCLOUD_URL']
REDIS_CHAN = 'chat'

app = Flask(__name__)
app.debug = 'DEBUG' in os.environ

sockets = Sockets(app)
redis_client = redis.from_url(REDIS_URL)


class ChatBackend(object):
    """Interface for registering and updating WebSocket clients.
    """
    def __init__(self):
        self.ws_list = []  # web-sockets
        self.pubsub = redis_client.pubsub()
        self.pubsub.subscribe(REDIS_CHAN)

    def register(self, client):
        """Register a WebSocket connection for Redis updates.
        """
        self.ws_list.append(client)

    def send(self, client, data):
        """Send given data to the registered client. Automatically discards invalid connections.
        """
        try:
            client.send(data)
        except Exception:
            self.ws_list.remove(client)

    def _iter_data(self):
        # listen for messages
        for message in self.pubsub.listen():
            data = message.get('data')
            if message['type'] == 'message':
                app.logger.info(u'Sending message: {}'.format(data))
                yield data

    def run(self):
        """Listens for new messages in Redis, and sends them to clients.
        """
        for data in self._iter_data():
            for client in self.ws_list:
                gevent.spawn(self.send, client, data)

    def start(self):
        """Maintains Redis subscription in the background."""
        gevent.spawn(self.run)


chats = ChatBackend()
chats.start()


# @app.route('/user/id/<int:user_id>')
# def profile(user_id):

@app.route('/notify', methods=['POST'])
def notify(ws):
    """The client sends chat messages, they are received here and inserted into Redis.
    """
    data = request.get_json(force=True)
    message = data['message']

    app.logger.info(u'Inserting message: {}'.format(message))
    redis_client.publish(REDIS_CHAN, message)


@sockets.route('/subscribe')
def inbox(ws):
    """The client is sent outgoing chat messages, via `ChatBackend`.
    """
    chats.register(ws)

    while ws.socket is not None:
        # Context switch while `ChatBackend.start` is running in the background.
        gevent.sleep()
