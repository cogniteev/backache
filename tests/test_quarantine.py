import os.path as osp
import unittest

from celery.result import AsyncResult
import yaml

import backache
from backache.antioxidant import (
    CeleryCache,
    ProcessingInQuarantineException,
)
from . celery_utils import (
    celery,
    get_tasks_results_collector_tasks,
    TasksResultsCollector,
)


class TestQuarantine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = osp.splitext(__file__)[0] + '.yml'
        with open(path) as istr:
            config = yaml.load(istr)
        config.update({
            'operations': {
                'op': cls._op,
            },
            'celery_app': celery,
            'callbacks': {
                'default': cls._processing_callback,
            },
        })
        celery.config_from_object(config['celery'])
        cls.results = get_tasks_results_collector_tasks()
        # force mitigation so that operations are executed in the
        # `bulk_get_or_delegate` member method.
        config['mitigation'] = lambda _: True

        @celery.task(name='backache.ut.quarantine_task')
        def quarantine_callback(operation, uri, cb_args, exc):
            TasksResultsCollector.add_quarantine_task(
                operation, uri, cb_args, exc
            )
        # register quarantine celery task
        config['celery']['quarantine_task'] = quarantine_callback
        cls.backache_config = config

    @classmethod
    def _backache(cls, with_celery=False):
        if with_celery:
            return backache.celerize(**cls.backache_config)
        else:
            return backache.Backache(**cls.backache_config)

    def setUp(self):
        """cleanup Mongo, Redis, and results collector between 2 tests"""
        b = self._backache()
        self.results.clear_results.apply_async().get()
        b._config.cache.clear()
        for i in range(0, 5):
            b._config.resource.delete('op', 'key%s' % i)

    def test_error_handling_without_celery(self):
        """Test core API error handling"""
        b = self._backache()
        misses, errors = b.bulk_get_or_delegate(
            self.BULK_COMMANDS,
            self._bulk_results_callback
        )
        self.assertTrue(len(misses) == 0, "mitigation is not working")
        # `retry` method is not available in `OperationContext` is
        # non-Celery mode, which explains the AttributeError
        self.assertEqual(len(errors), 4)
        errors = dict((e.uri, e.exc) for e in errors)
        self.assertIsInstance(errors['key1'], AttributeError)
        self.assertIsInstance(errors['key2'], AttributeError)
        self.assertIsInstance(errors['key3'], Exception)

    def test_error_handling_with_celery(self):
        """Test celery error handling"""
        b = self._backache(with_celery=True)
        for i in range(len(self.BULK_COMMANDS)):
            # Simulate a previous query for the same operation ('op', 'key$i')
            super(CeleryCache, b).get_or_delegate(
                'op', 'key%s' % i, 'other%s' % i
            )
        misses = b.bulk_get_or_delegate(
            self.BULK_COMMANDS,
            self._bulk_results_callback
        )
        for t in misses:
            self.assertIsInstance(t, AsyncResult)
            t.get()
        self.assertEqual(len(TasksResultsCollector.bulk_cache_hit_results), 1)
        cache_hit_result = TasksResultsCollector.bulk_cache_hit_results[0]
        self.assertIn(('op', 'key0'), cache_hit_result)
        self.assertEqual(cache_hit_result[('op', 'key0')]['result'], 'KEY0')
        self.assertItemsEqual(
            cache_hit_result[('op', 'key0')]['cb_args'],
            ['arg0', 'other0'],
            "Mitigation is forced, computation must " +
            "have been done by this process"
        )
        async_result = self.results.processing_callbacks.apply_async().get()
        self.assertTrue(len(async_result), 1)
        self.assertEqual(async_result[0]['result'], 'KEY4')
        self.assertItemsEqual(async_result[0]['cb_args'], ['arg4', 'other4'])

        quarantine_tasks = self.results.quarantine_tasks.apply_async().get()
        self.assertEqual(len(quarantine_tasks), 3)
        quarantine_tasks = dict((q['uri'], q) for q in quarantine_tasks)
        self.assertEqual(len(quarantine_tasks), 3)
        for key, task in quarantine_tasks.items():
            _id = key[-1:]
            self.assertItemsEqual(
                task['cb_args'], ['arg%s' % _id, 'other%s' % _id]
            )
            if key == 'key1':
                self.assertIsInstance(
                    task['exc'],
                    ProcessingInQuarantineException
                )
                self.assertEqual(task['exc'].kwargs, {'foo': 'bar'})
                self.assertEqual(task['exc'].op_kwargs, {'attempt': 3})
            elif key == 'key2':
                self.assertIsInstance(
                    task['exc'],
                    ProcessingInQuarantineException
                )
                self.assertEqual(task['exc'].op_kwargs, {})
            elif key == 'key3':
                self.assertIsInstance(task['exc'], Exception)

    BULK_COMMANDS = dict(
        (('op', 'key%s' % i), {'cb_args': ('arg%s' % i,)})
        for i in range(0, 5)
    )

    @classmethod
    def _op(cls, uri, context, attempt=1):
        """Operation used by this test. Behavior differs according to the
        `uri` value:

        - "key0": returns "KEY0" (`str.upper` operation)
        - "key1": ask retry until the 2nd attempt, then ask to move the
          task in quarantine
        - "key2": immediately move the task in quarantine
        - "key3": raise an instance of `Exception`, no matter what

        - "key4": ask retry until the 3rd attempt, then return "KEY1"
        """
        if uri == 'key1':
            if attempt != 3:
                raise context.retry(countdown=0, attempt=attempt + 1)
            raise context.quarantine(foo='bar')
        elif uri == 'key2':
            raise context.quarantine()
        elif uri == 'key3':
            raise Exception("Unmanaged exception")
        elif uri == 'key4':
            if attempt != 3:
                raise context.retry(countdown=0, attempt=attempt + 1)
        return uri.upper()

    def _bulk_results_callback(self, results):
        """Operation called by `bulk_get_or_delegate` member method with
        results of operations whose result was already in the cache.
        As backache is here configured in mitigation with an empty cache,
       `bulk_get_or_delegate` member method will process all operations,
        and results might fall here.
        """
        TasksResultsCollector.add_bulk_cache_hit_results(results)

    @classmethod
    def _processing_callback(cls, result, cb_args):
        TasksResultsCollector.add_processing_callback(result, cb_args)


if __name__ == '__main__':
    unittest.main()
