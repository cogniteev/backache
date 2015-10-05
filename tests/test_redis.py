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

    def test_pool_connect(self, **kwargs):
        pool = redis.ConnectionPool(host='localhost', port=6379, db=0)
        return self._connect(pool=pool, **kwargs)

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
        store.pop('op', u'ur\xed')
        self.assertTrue(store.add('op', u'ur\xed', 'foo'))
        self.assertFalse(store.add('op', u'ur\xed', 'foo'))
        self.assertFalse(store.add('op', u'ur\xed', 'foobar'))
        self.assertFalse(store.add('op', u'ur\xed', 'foo', 'plop', 'foobar'))
        store.pop('op', u'ur\xed')
        self.assertTrue(store.add('op', u'ur\xed', 'foo'))

    class ErrorGenerator(object):
        def __init__(self, reply, attempt_before_success):
            self.attempt_before_success = attempt_before_success
            self.reply = reply
            self.attempt = 0

        def __call__(self):
            self.attempt += 1
            if self.attempt < self.attempt_before_success:
                raise Exception("error-generator")
            return self.reply

    def test_redis_retry(self):
        store = self.test_pool_connect(retry_policy={
            'max_retries': 2,
            'interval_start': 0,
            'interval_step': 2,
            'interval_max': 1,
        })
        self.assertEqual(42, store._execute(self.ErrorGenerator(42, 3)))
        with self.assertRaises(Exception) as exc:
            store._execute(self.ErrorGenerator(42, 4))
        self.assertEqual(
            exc.exception.message,
            'error-generator'
        )


if __name__ == '__main__':
    unittest.main()
