"""
A chat server using WebSockets.

    gunicorn chat:app --config=gunicorn_settings.py
"""
import redis
import gevent
import flask
from flask import request

import flask_websockets


REDIS_URL = 'redis://127.0.0.1:6379/0'
redis_client = redis.from_url(REDIS_URL)

app = flask.Flask(__name__)
websockets = flask_websockets.create_websockets_app(app, redis_client)


@app.route('/')
def hello():
    return flask.render_template('index.html')


@app.route('/<channel>', methods=('GET', 'POST'))
def chat(channel):
    if request.method == 'GET':
        return flask.render_template('room.html', channel=channel)
    else:
        message = request.get_data()
        websockets.publish_message(message, channel)
        return flask.Response("OK")


@websockets.route('/<channel>')
def channel(websocket, channel):
    """Receive chat messages the client wants to publish.
    Each message is PUBLISHed so the SUBSCRRBEd clients can be sent it.
    """
    websockets.subscribe_client(websocket, channel)
    while not websocket.closed:
        gevent.sleep(0.1)  # switch to send messages
        message = websocket.receive()
        if message:
            websockets.publish_message(message, channel)
