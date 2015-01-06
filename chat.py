"""
A chat server using WebSockets.

    gunicorn chat:websockets --config=gunicorn_settings.py
"""
import flask

import websocket_channels


REDIS_URL = 'redis://127.0.0.1:6379/0'

app = flask.Flask(__name__)
websockets = websocket_channels.WebSocketMiddleware(app, REDIS_URL)


@app.route('/')
def home_view():
    return flask.render_template('home.html')


@app.route('/<path:channel>', methods=('GET', 'POST'))
def channel_view(channel):
    if flask.request.method == 'GET':
        return flask.render_template('channel.html', channel=channel.rstrip('/'))
    else:
        message = flask.request.get_data()
        websockets.publish_message(message, channel)
        if channel.endswith('/'):
            response = u'Sending message to clients on sub-channels of %s: %s' % (channel, message)
        else:
            response = u'Sending message to clients on channel %s: %s' % (channel, message)
        return flask.Response(response)
