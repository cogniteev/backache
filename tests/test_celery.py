import os.path as osp
import unittest

from celery import Celery
from celery.result import AsyncResult
import yaml

import backache

celery = Celery()


def to_upper(arg, context):
    return arg.upper()


@celery.task(name='backache.celery_callback')
def celery_cb(args, returned_value):
    result, cb_args = args
    result = {
        'result': result,
        'cb_args': cb_args,
    }
    TestCelery.callback.calls.append(result)
    return returned_value


@celery.task(name='backache.celery_fixed_result_callback')
def celery_fixed_result_cb(args):
    result, cb_args = args
    result = {
        'result': result,
        'cb_args': cb_args,
    }
    TestCelery.callback.calls.append(result)
    return 'fixed-result'


class TestCelery(unittest.TestCase):

    class Callback(object):
        def __init__(self):
            self.calls = []

        def process(self, result, cb_args):
            result = {
                'result': result,
                'cb_args': cb_args,
            }
            self.calls.append(result)
            return result

    callback = Callback()

    @classmethod
    def setUpClass(cls):
        path = osp.splitext(__file__)[0] + '.yml'
        with open(path) as istr:
            raw_config = yaml.load(istr)
        config = {
            'cache': raw_config['backache']['mongo'],
            'resource': raw_config['backache']['redis'],
            'celery': raw_config['backache']['celery'],
            'callbacks': {
                'default': cls.callback.process,
            },
            'celery_app': celery,
        }
        celery.config_from_object(raw_config['celery'])
        cls.backache = backache.celerize(**config)

    def setUp(self):
        TestCelery.callback.calls = []
        self.backache._config.callbacks.operations.pop('toupper', None)

    def test_01_unknown_operation(self):
        """Celery mode with missing operation"""
        self.backache._config.cache.clear()
        self.backache._config.resource.delete('toupper', 'foobar')
        # Celery is in eager mode for unit-tests. In the real world,
        # the exception raised by the callback is not seen like here.
        with self.assertRaises(Exception) as exc:
            self.backache.get_or_delegate('toupper', 'foobar', u'\xedtem1')
        self.assertEqual(exc.exception.message, "Unknown operation 'toupper'")

    def test_02_upper_function(self):
        """Celery mode - classic function"""
        t = self.backache
        t._config.cache.clear()
        t._config.resource.delete('toupper', 'foobar')
        t._config.operations['toupper'] = to_upper
        chain_task = t.get_or_delegate('toupper', 'foobar', u'\xedtem1')
        self.assertIsInstance(chain_task, AsyncResult)
        self.assertEqual(
            chain_task.get(),
            {
                'cb_args': [u'\xedtem1'],
                'result': 'FOOBAR',
            }
        )
        # ensure callback has been called
        self.assertEqual(
            self.callback.calls,
            [{'cb_args': [u'\xedtem1'], 'result': 'FOOBAR'}]
        )
        # now result is in cache, get_or_delegate directly provides the result
        consume_task = t.get_or_delegate('toupper', 'foobar',
                                         'item2', 'item3')
        self.assertEqual(consume_task, 'FOOBAR')

    def test_03_celery_signature_callback(self):
        t = self.backache
        t._config.cache.clear()
        t._config.resource.delete('toupper', 'foobar')
        t._config.callbacks.operations['toupper'] = celery_cb.s(42)
        chain_task = t.get_or_delegate('toupper', 'foobar', u'\xedtem1')
        self.assertIsInstance(chain_task, AsyncResult)
        # ensure result if what the final callback returned
        self.assertEqual(chain_task.get(), 42)
        self.assertEqual(
            self.callback.calls,
            [{'result': 'FOOBAR', 'cb_args': [u'\xedtem1']}]
        )

    def test_04_celery_task_callback(self):
        t = self.backache
        t._config.cache.clear()
        t._config.resource.delete('toupper', 'foobar')
        t._config.callbacks.operations['toupper'] = celery_fixed_result_cb
        chain_task = t.get_or_delegate('toupper', 'foobar', u'\xedtem1')
        self.assertIsInstance(chain_task, AsyncResult)
        # ensure result if what the final callback returned
        self.assertEqual(chain_task.get(), 'fixed-result')
        self.assertEquals(
            self.callback.calls,
            [{'result': 'FOOBAR', 'cb_args': [u'\xedtem1']}]
        )


if __name__ == '__main__':
    unittest.main()
