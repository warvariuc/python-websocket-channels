"""
A chat server using WebSockets.

    gunicorn chat:websockets --config=gunicorn_settings.py
"""
import json

import flask

import websocket_channels


REDIS_URL = 'redis://127.0.0.1:6379/0'

app = flask.Flask(__name__)
websockets = websocket_channels.WebSocketMiddleware(app, REDIS_URL)


@app.route('/')
def home_view():
    return flask.render_template('home.html')


@app.route('/channel/<path:channel>')
def channel_view(channel):
    return flask.render_template('channel.html', channel=channel.rstrip('/'))


@app.route('/publish', methods=('POST',))
def publish_messages_view():
    """Publish given messages on the given channels. The POST body should be in form of
    {channel: message, ...}
    """
    data = json.loads(flask.request.get_data())
    for channel, message in data.iteritems():
        websockets.publish_message(message, channel)
    return flask.Response('OK')
