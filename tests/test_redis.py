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
        self._connect(pool=pool)

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


if __name__ == '__main__':
    unittest.main()
