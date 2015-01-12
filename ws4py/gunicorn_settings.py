# https://github.com/benoitc/gunicorn/blob/master/examples/example_config.py

bind = '127.0.0.1:9000'
worker_class = 'echo_gevent_server.Worker'
workers = 1  # number of worker process for handling requests
worker_connections = 1000  # maximum number of simultaneous clients
logconfig = 'logging.conf'
timeout = 30
# add current directory to python path, because gunicorn doesn't do this
pythonpath = '.'
