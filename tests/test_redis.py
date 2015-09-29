import os
import unittest

import redis

from backache.resource import RedisStore


class TestRedis(unittest.TestCase):
    def test_strict_connect(self):
        self._connect(**{
            'strict': {
                'host': 'localhost',
                'port': '6379',
                'db': 0,
            }
        })

    def test_pool_connect(self):
        pool = redis.ConnectionPool(host='localhost', port=6379, db=0)
        return self._connect(pool=pool)

    @unittest.skipIf(
        os.environ.get('TRAVIS_CI_BUILD') is not None,
        'Disabled because Sentinel is not available on Travis-CI'
    )
    def test_sentinel_connect(self):
        self._connect(**{
            'sentinels': [
                {
                    'host': 'localhost',
                    'port': 26379,
                }
            ],
            'master': 'rabbit',
        })

    def _connect(self, **config):
        store = RedisStore(**config)
        self.assertTrue(store.ping())
        return store

    def test_add_operation(self):
        store = self.test_pool_connect()
        store.pop('op', 'uri')
        self.assertTrue(store.add('op', 'uri', 'foo'))
        self.assertFalse(store.add('op', 'uri', 'foo'))
        self.assertFalse(store.add('op', 'uri', 'foobar'))
        self.assertFalse(store.add('op', 'uri', 'foo', 'plop', 'foobar'))
        store.pop('op', 'uri')
        self.assertTrue(store.add('op', 'uri', 'foo'))


if __name__ == '__main__':
    unittest.main()
