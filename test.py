from gevent import monkey; monkey.patch_all()

import argparse
import time
import gevent
from ws4py.client import WebSocketBaseClient
from ws4py import configure_logger


logger = configure_logger(level='WARNING')

stats = {}
# TODO: check that other clients from the same channel received the message


class WebSocketClient(WebSocketBaseClient):

    def __init__(self, client_id, url, *args, **kwargs):
        self.client_id = client_id
        self.stats = stats.setdefault(self.client_id, {})
        self.errors = self.stats.setdefault('errors', {})
        self.message_count = 0
        super(WebSocketClient, self).__init__(url, *args, **kwargs)

    def get_new_message(self):
        self.message_count += 1
        return 'Message #{:<3} from client #{:<5}'.format(self.message_count, self.client_id)

    def connect(self):
        self.stats['handshake_started_at'] = time.time()
        return super(WebSocketClient, self).connect()

    def handshake_ok(self):
        self.stats['handshake_done_at'] = time.time()
        # logger.info("Opened #%s %s", self.client_id, format_addresses(self))
        # time.sleep(random.random() * 1)
        self.stats['message_sent_at'] = time.time()
        self.send(self.get_new_message())
        self.stats['message_sent_at2'] = time.time()

    def received_message(self, msg):
        self.stats['echo_message_received_at'] = time.time()
        self.close()


def calculate_stats(array):
    """Return min, max, avg in the given array.
    """
    _count = 0
    _max = _sum = 0.0
    _min = None
    for number in array:
        _count += 1
        if _min is None or number < _min:
            _min = number
        if number > _max:
            _max = number
        _sum += number
    return {'min': _min, 'max': _max, 'avg': _sum / _count}
        

CLIENT_COUNT = 2000
WS_CHANNEL_URL = 'ws://127.0.0.1:9000/ws/client/{client_id}'

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='WebSocket Channels test')
    parser.add_argument('--clients', default=CLIENT_COUNT, type=int)
    # parser.add_argument('-p', '--port', default=5000, type=int)
    args = parser.parse_args()

    threads = []
    
    for i in xrange(args.clients):
        
        def run_client(client_id):
            client = WebSocketClient(client_id, WS_CHANNEL_URL.format(client_id=client_id))
            client.connect()
            client.run()
            
        threads.append(gevent.Greenlet(run_client, i))

    print "%d clients were created\n" % (i + 1)

    start_time = time.time()

    for thread in threads:
        thread.start()

    gevent.joinall(threads)

    print "Clients finished in {:.2f} sec.\n".format(time.time() - start_time)

    print """Handshake times (msec):
  Average: {avg:10.2f}    Min: {min:10.2f}    Max: {max:10.2f}
""".format(**calculate_stats(
        (_stats['handshake_done_at'] - _stats['handshake_started_at']) * 1000
        for _stats in stats.itervalues()))

    print """Echo response times (msec):
  Average: {avg:10.2f}    Min: {min:10.2f}    Max: {max:10.2f}
""".format(**calculate_stats(
        (_stats['echo_message_received_at'] - _stats['message_sent_at']) * 1000
        for _stats in stats.itervalues()))

    errors = {}
    for _stats in stats.itervalues():
        for error_code, error_count in _stats['errors'].iteritems():
            errors[error_code] = errors.get(error_code, 0) + error_count
    if errors:
        print "Errors:"
        for error_code, error_count in errors.iteritems():
            print "  {}: {}".format(error_code, error_count)
