"""
A chat server using WebSockets.

    gunicorn chat:websockets --config=gunicorn_settings.py
"""
import flask
from flask import request

import flask_websockets


REDIS_URL = 'redis://127.0.0.1:6379/0'

app = flask.Flask(__name__)
websockets = flask_websockets.WebSocketMiddleware(app, REDIS_URL)


@app.route('/')
def hello():
    return flask.render_template('index.html')


@app.route('/<path:channel>', methods=('GET', 'POST'))
def chat(channel):
    if request.method == 'GET':
        return flask.render_template('room.html', channel=channel)
    else:
        message = request.get_data()
        websockets.publish_message(message, channel)
        return flask.Response("OK")
