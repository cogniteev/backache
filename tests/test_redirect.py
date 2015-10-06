import os.path as osp
import unittest

from celery import Celery
from celery.result import AsyncResult
import yaml

import backache

celery = Celery()


class TestRedirect(unittest.TestCase):
    # A -> B -> C -> D
    #      ^
    #      |
    #      E
    #      ^
    #      |
    #      F
    REDIRECTS = {
        'A': 'B',
        'B': 'C',
        'C': 'D',
        'F': 'E',
        'E': 'B',
    }
    OPERATION_COMPUTED_COUNT = 0

    @classmethod
    def operation(cls, uri, context):
        r = cls.REDIRECTS.get(uri)
        while r is not None:
            res = context.get_or_add_redirect(r)
            if res:
                return res
            r = cls.REDIRECTS.get(r)

        cls.OPERATION_COMPUTED_COUNT += 1
        return 'foobar'

    @classmethod
    def setUpClass(cls):
        path = osp.splitext(__file__)[0] + '.yml'
        with open(path) as istr:
            raw_config = yaml.load(istr)
        config = {
            'cache': raw_config['backache']['mongo'],
            'resource': raw_config['backache']['redis'],
            'celery': raw_config['backache']['celery'],
            'celery_app': celery,
        }
        celery.config_from_object(raw_config['celery'])
        cls.backache = backache.celerize(**config)
        cls.backache._config.operations['foo'] = cls.operation

    def setUp(self):
        self.backache._config.cache.clear()
        for l in 'ABCDE':
            self.backache._config.resource.delete('foo', l)
        TestRedirect.OPERATION_COMPUTED_COUNT = 0

    def test_update_chain(self):
        task = self.backache.get_or_delegate('foo', 'A', 'item1')
        self.assertIsInstance(task, AsyncResult)
        self.assertEqual(task.get(), ('foobar', ['item1']))
        self.assertEqual(
            self.backache.get_or_delegate('foo', 'B', 'item2'),
            'foobar'
        )
        self.assertEqual(
            self.backache.get_or_delegate('foo', 'C', 'item2'),
            'foobar'
        )
        self.assertEqual(
            self.backache.get_or_delegate('foo', 'D', 'item2'),
            'foobar'
        )
        self.assertEqual(self.OPERATION_COMPUTED_COUNT, 1)

    def test_reuse_set(self):
        self.backache.get_or_delegate('foo', 'A', 'item3').get()
        self.assertEqual(1, self.OPERATION_COMPUTED_COUNT)
        task = self.backache.get_or_delegate('foo', 'F', 'item4')
        self.assertEqual(task.get(), ('foobar', ['item4']))
        self.assertEqual(1, self.OPERATION_COMPUTED_COUNT)
        self.assertEqual(
            self.backache.get_or_delegate('foo', 'E', 'item5'),
            'foobar'
        )
        self.assertEqual(1, self.OPERATION_COMPUTED_COUNT)


if __name__ == '__main__':
    unittest.main()
