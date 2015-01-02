"""
A chat server using WebSockets.

    gunicorn chat:app --config=gunicorn_settings.py
"""
import redis
import gevent
import flask

import flask_websockets


REDIS_URL = 'redis://127.0.0.1:6379/0'
redis_client = redis.from_url(REDIS_URL)

app = flask.Flask(__name__)
websockets = flask_websockets.create_websockets_app(app, redis_client)


@app.route('/')
def hello():
    return flask.render_template('index.html')


@app.route('/<channel>')
def chat(channel):
    return flask.render_template('room.html', channel=channel)


@websockets.route('/<channel>')
def channel(websocket, channel):
    """Receive chat messages the client wants to send to others.
    The message is PUBLISHed so the SUBSCIRBEd clients can receive it.
    """
    websockets.subscribe_client(websocket, channel)
    while not websocket.closed:
        gevent.sleep(0.1)  # switch to send messages

        message = websocket.receive()
        if message:
            websockets.publish_message(message, channel)
