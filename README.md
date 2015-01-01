Websockets chat in Python demo
==============================

This is a simple Websockets server written in Python using Flask + gevent-websocket.

The idea was taken from https://devcenter.heroku.com/articles/python-websockets

The dependencies were updated and the code was simplified as possible.

The middleware was refactored to allow URL to include variable parts.

It uses Redis Pub/Sub subsystem to ensure that all connected clients recieve the message, 
even if there are several Gunicorn workers.
