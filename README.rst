WebSocket channels in Python
============================

This is a simple WebSocket server written in Python using Flask + gevent-websocket.

Inspired by https://devcenter.heroku.com/articles/python-websockets and https://github.com/kennethreitz/flask-sockets

The middleware is not Flask specific, it can be used around any WSGI application.

The server uses `Redis Pub/Sub subsystem <https://github.com/andymccurdy/redis-py#publish--subscribe>`_
to ensure that all connected clients recieve the message, even if there are several Gunicorn
workers/machines:

.. code:: bash

    $ gunicorn chat:websockets --config=gunicorn_settings.py --workers=2 --worker-connections=2

    2015-01-03 11:09:03 [30648] [INFO] Starting gunicorn 19.1.1
    2015-01-03 11:09:03 [30648] [INFO] Listening at: http://127.0.0.1:5000 (30648)
    2015-01-03 11:09:03 [30648] [INFO] Using worker: websocket_channels.Worker
    2015-01-03 11:09:03 [30653] [INFO] Booting worker with pid: 30653
    2015-01-03 11:09:03 [30654] [INFO] Booting worker with pid: 30654
    2015-01-03 11:09:08 [30653] [INFO] Pusblishing message to channel chat: {"handle":"","text":"test"}
    2015-01-03 11:09:08 [30654] [INFO] Sending message to clients on channel chat: {"handle":"","text":"test"}
    2015-01-03 11:09:08 [30653] [INFO] Sending message to clients on channel chat: {"handle":"","text":"test"}


Running the server:

.. code:: bash

    $ gunicorn chat:websockets --config=gunicorn_settings.py


You can send a message to a room (visit http://127.0.0.1:5000/users/1 ) using an HTTP POST request:

.. code:: bash

    $ curl 'http://127.0.0.1:5000/users/1' -d 'Hi there!'


You can send a message to all sub-rooms using trailing slash:

.. code:: bash

    $ curl 'http://127.0.0.1:5000/users/' -d 'Hi there!'


Sample Nginx conf:

.. code:: nginx
    
    upstream websocket {
        server 127.0.0.1:5000;
    }

    server {
        ...

        location ~ /ws/(?<rest>.+) {
            proxy_pass http://websocket/$rest;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "Upgrade";
        }
    }


Then in Chrome Console you could do something like:

.. code:: javascript

    > $.getScript('//rawgit.com/joewalnes/reconnecting-websocket/master/reconnecting-websocket.js');
    < Object {readyState: 1, getResponseHeader: function, getAllResponseHeaders: function, setRequestHeader: function, overrideMimeType: function…}
    > var socket = new ReconnectingWebSocket("ws://"+ location.host + "/ws/channel");
    < undefined
    > socket.onmessage = function(message) { console.log(message.data); };
    < function (message) { console.log(message.data); }


And send a message to the browser:

.. code:: bash

    $ curl 'http://localhost:5000/channel' -d '{"text": "Hi there!"}'

