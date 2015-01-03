# https://github.com/benoitc/gunicorn/blob/master/examples/example_config.py

bind = '127.0.0.1:5000'

worker_class = 'flask_websockets.Worker'
workers = 1  # number of worker process for handling requests
worker_connections = 1000  # maximum number of simultaneous clients
logconfig = 'logging.conf'
timeout = 30

# add current directory to python path, because gunicorn doesn't do this
import sys
sys.path.insert(0, '.')
