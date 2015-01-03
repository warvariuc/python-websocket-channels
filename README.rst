WebSockets chat in Python
=========================

This is a simple Websockets server written in Python using Flask + gevent-websocket.

The idea was taken from https://devcenter.heroku.com/articles/python-websockets

The middleware allows URLs to include variable parts.

The server uses `Redis Pub/Sub subsystem <https://github.com/andymccurdy/redis-py#publish--subscribe>`_
to ensure that all connected clients recieve the message, even if there are several Gunicorn
workers/machines::

    $ gunicorn chat:app --config=gunicorn_settings.py --workers=2 --worker-connections=2

    2015-01-03 11:09:03 [30648] [INFO] Starting gunicorn 19.1.1
    2015-01-03 11:09:03 [30648] [INFO] Listening at: http://127.0.0.1:8000 (30648)
    2015-01-03 11:09:03 [30648] [INFO] Using worker: flask_websockets.Worker
    2015-01-03 11:09:03 [30653] [INFO] Booting worker with pid: 30653
    2015-01-03 11:09:03 [30654] [INFO] Booting worker with pid: 30654
    2015-01-03 11:09:08 [30653] [INFO] Pusblishing message to channel chat: {"handle":"","text":"test"}
    2015-01-03 11:09:08 [30654] [INFO] Sending message to clients on channel chat: {"handle":"","text":"test"}
    2015-01-03 11:09:08 [30653] [INFO] Sending message to clients on channel chat: {"handle":"","text":"test"}


Running the server::

    gunicorn chat:app --config=gunicorn_settings.py

You can send a message to a room using an HTTP POST request::

    curl 'http://localhost:8000/test' -d '{"handle": "POST", "text": "Hi there!"}'

