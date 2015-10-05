from functools import partial
import itertools
import logging
import pickle
import time

from redis.sentinel import Sentinel
from redis import StrictRedis, Redis

from . utils import nameddict


class ResourceStore(object):  # pragma: no cover
    def clear(self, operation, uri):
        """Atomically retrieves the value of the key associated to the
        specified URL and remove it from redis

        :return: Redis set value, may return an empty tuple if there is no
        such key or the set is empty.
        :rtype: tuple
        """
        raise NotImplementedError()

    def add(self, operation, uri, *payloads):
        """Insert payloads in set for the given (operation, uri) key

        :return:
          `True` if there was no previous pending task registered for the
          given key and operation, `False` otherwise.
        :rtype: boolean
        """

    def count(self, operation, uri):
        """ Provides number of payloads for the given operation and uri
        """

    def ping(self):
        pass


class RedisStore(ResourceStore):
    RETRY_POLICY = {
        'max_retries': 0,  # Inf
        'interval_start': 0,
        'interval_step': 1,
        'interval_max': 60,
    }

    def __init__(self, **kwargs):
        super(RedisStore, self).__init__()
        self._retry = nameddict(kwargs.get('retry_policy', self.RETRY_POLICY))
        if 'strict' in kwargs:
            self._redis = StrictRedis(**kwargs['strict'])
        elif 'pool' in kwargs:
            self._redis = Redis(connection_pool=kwargs['pool'])
        elif 'sentinels' in kwargs:
            sentinels = kwargs.get('sentinels', [{
                'host': 'localhost',
                'port': 26379
            }])
            sentinels = map(lambda d: (d['host'], d['port']), sentinels)
            self._master = kwargs.get('master', 'backache')
            self._sentinel = Sentinel(sentinels)
            self._redis = self._sentinel_connect()
            self._error_cb = self._sentinel_error_cb
        self._uri = unicode(kwargs.get('uri', 'backache://{operation}/{uri}'))
        self._logger = logging.getLogger('backache.redis')

    def delete(self, operation, uri):
        return self._execute(
            self._redis.delete,
            self._key(operation, uri)
        )

    def pop(self, operation, uri):
        key = self._key(operation, uri)
        pipe = self._redis.pipeline()
        pipe.sdiff(key, self._unknown_key())
        pipe.delete(key)
        payloads, _ = self._execute(pipe.execute)
        return [pickle.loads(e) for e in payloads]

    def add(self, operation, uri, *payloads):
        key = self._key(operation, uri)
        pipe = self._redis.pipeline()
        pipe.scard(key)
        pipe.sadd(
            key,
            *[pickle.dumps(e) for e in payloads]
        )
        count_before, _ = self._execute(pipe.execute)
        return count_before == 0

    def count(self, operation, uri):
        return self._execute(partial(
            self._redis.scard,
            self._key(operation, uri)
        ))

    def ping(self):
        return self._execute(self._redis.ping)

    def _key(self, operation, uri):
        return self._uri.format(**{
            'operation': operation,
            'uri': uri,
        })

    def _unknown_key(self):
        return self._key('', '')

    def fxrange(self, start=1.0, stop=None, step=1.0):
        start = self._retry.interval_start
        stop = self._retry.interval_max + self._retry.interval_start
        step = self._retry.interval_step
        cur = start * 1.0
        while 1:
            if not stop or cur <= stop:
                yield cur
                cur += step
            else:
                yield cur - step

    def _execute(self, func, *args, **kwargs):
        interval_range = self.fxrange()
        max_retries = self._retry.max_retries
        for retries in itertools.count():
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self._error_cb(e)
                if max_retries and retries >= max_retries:
                    raise
                tts = next(interval_range)
                time.sleep(tts)

    def _error_cb(self, exc):
        self._logger.exception(exc)

    def _sentinel_error_cb(self, exc):
        self._logger.exception(exc)
        self._redis = self._sentinel_connect()

    def _sentinel_connect(self):
        return self._execute(
            self._sentinel.master_for,
            self._master
        )
