import os.path as osp
import unittest

from celery import Celery
from celery.result import AsyncResult
import yaml

import backache

celery = Celery()


class TestBulkOperation(unittest.TestCase):
    @classmethod
    def _backache(cls, with_celery=False, with_mitigation=False):
        path = osp.splitext(__file__)[0] + '.yml'
        with open(path) as istr:
            config = yaml.load(istr)
        config['operations'] = {
            'op1': cls._operation1,
            'op2': cls._operation2,
        }
        config['celery_app'] = celery
        if with_mitigation:
            config['mitigation'] = lambda _: True
        celery.config_from_object(config['celery'])
        if with_celery:
            return backache.celerize(**config)
        else:
            return backache.Backache(**config)

    def setUp(self):
        self._cache_hits_received = None
        b = self._backache()
        b._config.cache.clear()
        for i in range(1, 3):
            for j in range(1, 3):
                b._config.resource.delete('op%s' % i, 'key%s' % j)

    def test_without_celery(self):
        commands = {
            ('op1', 'key1'): {'cb_args': ('arg1', 'arg2')},
            ('op2', 'key2'): {'cb_args': ('arg3', 'arg4')},
        }
        b = self._backache()
        cache_misses, errors = b.bulk_get_or_delegate(
            commands, self._cache_hits_cb
        )
        self.assertEqual(errors, [])
        self.assertEqual(self._cache_hits_received, {})
        self.assertItemsEqual(
            cache_misses,
            [('op1', 'key1', False), ('op2', 'key2', False)]
        )
        result, cb_args = b.consume('op1', 'key1')
        self.assertEqual(errors, [])
        self.assertEquals(result, 'op1-key1')
        self.assertItemsEqual(cb_args, ['arg1', 'arg2'])

        cache_misses, errors = b.bulk_get_or_delegate(
            commands, self._cache_hits_cb
        )
        self.assertEqual(
            cache_misses,
            [('op2', 'key2', True)]
        )
        self.assertEqual(
            self._cache_hits_received,
            {
                ('op1', 'key1'): {
                    'cb_args': ('arg1', 'arg2'),
                    'result': 'op1-key1',
                },
            }
        )

    def test_without_celery_mitigation(self):
        b = self._backache(with_mitigation=True)
        commands = {
            ('op1', 'key1'): {'cb_args': ('arg1', 'arg2')},
            ('op2', 'key2'): {'cb_args': ('arg3', 'arg4')},
        }
        self.assertEqual(
            b.bulk_get_or_delegate(commands, self._cache_hits_cb),
            ([], [])
        )
        self.assertEqual(len(self._cache_hits_received), 2)

    def test_with_celery_mitigation(self):
        commands = {
            ('op1', 'key1'): {'cb_args': ('arg1', 'arg2')},
            ('op2', 'key2'): {'cb_args': ('arg3', 'arg4')},
        }
        b = self._backache(with_celery=True, with_mitigation=True)
        cache_misses = b.bulk_get_or_delegate(commands, self._cache_hits_cb)
        self.assertEqual(cache_misses, [])
        self.assertEqual(len(self._cache_hits_received), 2)

    def test_with_celery(self):
        commands = {
            ('op1', 'key1'): {'cb_args': ('arg1', 'arg2')},
            ('op2', 'key2'): {'cb_args': ('arg3', 'arg4')},
        }
        b = self._backache(with_celery=True)
        cache_misses = b.bulk_get_or_delegate(commands, self._cache_hits_cb)
        self.assertEqual(self._cache_hits_received, {})
        results = []
        for cache_miss in cache_misses:
            self.assertIsInstance(cache_miss, AsyncResult)
            results.append(cache_miss.get())
        self.assertEqual(len(results), 2)
        seen_1st_result = seen_2nd_result = 0
        for result, cb_args in results:
            if result == 'op1-key1':
                self.assertItemsEqual(cb_args, ['arg1', 'arg2'])
                seen_1st_result += 1
            elif result == 'op2-key2':
                self.assertItemsEqual(cb_args, ['arg3', 'arg4'])
                seen_2nd_result += 1
        self.assertEqual(seen_1st_result, 1)
        self.assertEqual(seen_2nd_result, 1)

        commands[('op1', 'key2')] = {'cb_args': ('arg5',)}
        cache_misses = b.bulk_get_or_delegate(commands, self._cache_hits_cb)
        self.assertEqual(
            self._cache_hits_received,
            {
                ('op1', 'key1'): {
                    'cb_args': ('arg1', 'arg2'),
                    'result': 'op1-key1',
                },
                ('op2', 'key2'): {
                    'cb_args': ('arg3', 'arg4'),
                    'result': 'op2-key2',
                },
            }
        )
        self.assertEqual(len(cache_misses), 1)
        self.assertIsInstance(cache_misses[0], AsyncResult)
        self.assertEqual(cache_misses[0].get(), ('op1-key2', ['arg5']))

    def _cache_hits_cb(self, cache_hits):
        self._cache_hits_received = cache_hits

    @classmethod
    def _operation1(cls, uri, context):
        return 'op1-%s' % uri

    @classmethod
    def _operation2(cls, uri, context):
        return 'op2-%s' % uri


if __name__ == '__main__':
    unittest.main()
