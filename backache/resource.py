from functools import partial
import logging
import pickle
import time

from redis.sentinel import Sentinel, MasterNotFoundError
from redis import StrictRedis, Redis


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
    def __init__(self, **kwargs):
        super(RedisStore, self).__init__()
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
            self._retry = self._sentinel_retry
        self._uri = kwargs.get('uri', 'backache://{operation}/{uri}')
        self._logger = logging.getLogger('backache.redis')

    def delete(self, operation, uri):
        return self._retry(
            self._redis.delete,
            self._key(operation, uri)
        )

    def pop(self, operation, uri):
        key = self._key(operation, uri)
        pipe = self._redis.pipeline()
        pipe.sdiff(key, self._unknown_key())
        pipe.delete(key)
        payloads, _ = self._retry(pipe.execute)
        if payloads is None:
            return None
        else:
            return [pickle.loads(e) for e in payloads]

    def add(self, operation, uri, *payloads):
        key = self._key(operation, uri)
        pipe = self._redis.pipeline()
        pipe.scard(key)
        pipe.sadd(
            key,
            *[pickle.dumps(e) for e in payloads]
        )
        count_before, _ = self._retry(pipe.execute)
        return count_before == 0

    def count(self, operation, uri):
        return self._retry(partial(
            self._redis.scard,
            self._key(operation, uri)
        ))

    def ping(self):
        return self._retry(self._redis.ping)

    def _key(self, operation, uri):
        return self._uri.format(**{
            'operation': operation,
            'uri': uri,
        })

    def _unknown_key(self):
        return self._key('', '')

    def _retry(self, func, *args, **kwargs):
        for _ in range(3):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self._logger.exception(e)

    def _sentinel_retry(self, func, *args, **kwargs):
        for _ in range(3):
            try:
                return func(*args, **kwargs)
            except MasterNotFoundError:
                raise
            except Exception as e:
                self._logger.exception(e)
                self._redis = self._sentinel_connect()

    def _sentinel_connect(self):
        wait_time = 1
        max_wait_time = 64
        while True:
            try:
                return self._sentinel.master_for(self._master)
            except Exception as e:
                self._logger.exception(e)
                time.sleep(wait_time)
                wait_time = min(wait_time * 2, max_wait_time)
