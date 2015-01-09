import time

from ws4py.client import WebSocketBaseClient
from ws4py.manager import WebSocketManager
from ws4py import format_addresses, configure_logger


# TODO: test with ws4py echoserver and compare the results
logger = configure_logger(level='WARNING')

manager = WebSocketManager()

stats = {}
# TODO: check that other clients from the same channel received the message


class EchoClient(WebSocketBaseClient):

    def __init__(self, client_id, *args, **kwargs):
        self.client_id = client_id
        self.stats = stats.setdefault(self.client_id, {})
        super(EchoClient, self).__init__(*args, **kwargs)

    def connect(self):
        self.stats['connection_started_at'] = time.time()
        return super(EchoClient, self).connect()

    def handshake_ok(self):
        self.stats['handshake_done_at'] = time.time()
        # logger.info("Opened #%s %s", self.client_id, format_addresses(self))
        manager.add(self)
        self.stats['message_sent_at'] = time.time()
        self.send('a message')

    def received_message(self, msg):
        self.stats['message_received_at'] = time.time()
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
        

if __name__ == '__main__':

    try:
        manager.start()
        for i in xrange(2000):
            client = EchoClient(i, 'ws://localhost:5000/client/%s' % i)
            client.connect()

        # TODO: do they connect sequencially? How to connect in parallel?
        print "%d clients are connected" % (i + 1)

        while manager:
            for ws in manager:
                if not ws.terminated:
                    break
            time.sleep(3)
    except KeyboardInterrupt:
        manager.close_all()
        manager.stop()
        manager.join()

    print """Handshake times (msec):
Average: {avg:10.2f}
    Min: {min:10.2f}
    Max: {max:10.2f}
""".format(**calculate_stats(
        (_stats['handshake_done_at'] - _stats['connection_started_at']) * 1000 
        for _stats in stats.itervalues()))

    print """Echo response times (msec):
Average: {avg:10.2f}
    Min: {min:10.2f}
    Max: {max:10.2f}
""".format(**calculate_stats(
        (_stats['message_received_at'] - _stats['message_sent_at']) * 1000
        for _stats in stats.itervalues()))
