# add current directory to python path, because gunicorn doesn't do this
import sys
sys.path.insert(0, '.')

worker_class = 'flask_websockets.worker'
workers = 1  # number of worker process for handling requests
worker_connections = 1000  # maximum number of simultaneous clients
logconfig = 'logging.conf'
timeout = 300
