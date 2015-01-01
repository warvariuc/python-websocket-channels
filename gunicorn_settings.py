# add current directory to python path, because gunicorn doesn't do this
import sys
sys.path.insert(0, '.')

logconfig = 'logging.conf'
worker_class = 'flask_websockets.worker'
timeout = 300
