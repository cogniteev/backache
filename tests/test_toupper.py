import os.path as osp
import unittest

import mock
import yaml

import backache


class TestToUpper(unittest.TestCase):
    _cb_calls = []

    @classmethod
    def _backache(cls, with_callback=False):
        path = osp.splitext(__file__)[0] + '.yml'
        with open(path) as istr:
            raw_config = yaml.load(istr)
        options = {
            'cache': raw_config['mongo'],
            'resource': raw_config['redis'],
            'operations': {
                'toupper': lambda uri, _: uri.upper(),
            }
        }
        if with_callback:
            options['callbacks'] = {
                'default': cls._callback,
            }
        return backache.Backache(**options)

    def setUp(self):
        b = TestToUpper._backache()
        b._config.cache.clear()
        b._config.resource.delete('toupper', u'foobar\xed')
        b._config.resource.delete('buggy-operation', u'foobar\xed')

    def assertConsumeEqual(self, consume_result, expected):
        self.assertTrue(isinstance(consume_result, tuple))
        self.assertTrue(isinstance(expected, tuple))
        self.assertEqual(len(consume_result), len(expected))
        self.assertEqual(consume_result[0], expected[0])
        self.assertItemsEqual(consume_result[1], expected[1])

    def test_no_delay(self):
        b = TestToUpper._backache()
        self.assertEqual(
            b.get_or_delegate('toupper', u'foobar\xed', 'item1'),
            None  # result not in cache yet
        )
        self.assertEqual(
            b.get_or_delegate('toupper', u'foobar\xed', 'item2'),
            None  # same query but different callback arguments
        )
        self.assertConsumeEqual(
            b.consume('toupper', u'foobar\xed'),
            (u'FOOBAR\xcd', ['item1', 'item2'])
        )
        self.assertEqual(
            b.get_or_delegate('toupper', u'foobar\xed', 'item3'),
            u'FOOBAR\xcd'  # now, result is in cache
        )

    def test_consume_twice(self):
        b = TestToUpper._backache()
        b.get_or_delegate('toupper', u'foobar\xed', 'item1')
        self.assertEqual(
            b.consume('toupper', u'foobar\xed'),
            (u'FOOBAR\xcd', ['item1'])
        )
        # callback has been called
        self.assertEqual(
            self._cb_calls,
            [{'result': u'FOOBAR\xcd', 'cb_args': set(['item2', 'item1'])}]
        )
        self._cb_calls = []
        # no callback arguments because previously consumed
        self.assertEqual(
            b.consume('toupper', u'foobar\xed'),
            (u'FOOBAR\xcd', [])
        )
        self.assertEqual(self._cb_calls, [])
        # callback is not called because there is no callback argument
        self.assertEqual(
            b.consume('toupper', u'foobar\xed'),
            (u'FOOBAR\xcd', [])
        )
        self.assertEqual(self._cb_calls, [])

    def test_callback(self):
        b = TestToUpper._backache(with_callback=True)
        self.assertEqual(
            b.get_or_delegate('toupper', u'foobar\xed', 'item1'),
            None  # result not in cache yet
        )
        self.assertEqual(
            b.get_or_delegate('toupper', u'foobar\xed', 'item2'),
            None
        )
        # consume returns raw result
        res = b.consume('toupper', u'foobar\xed')
        self.assertEqual(res[0], u'FOOBAR\xcd')
        self.assertItemsEqual(res[1], ['item1', 'item2'])
        self.assertItemsEqual(
            self._cb_calls,
            [
                {'result': u'FOOBAR\xcd', 'cb_args': set(['item1', 'item2'])},
            ]
        )

    def test_consume_unknown_uri(self):
        """process uri without callback arguments

        Processing is not even launched
        """
        b = TestToUpper._backache(with_callback=True)
        self.assertEqual(
            b.consume('toupper', u'unknown_ur\xed'),
            (None, None)
        )

    def test_locked_resource(self):
        b = TestToUpper._backache(with_callback=True)
        b._config.cache.lock('toupper', u'foobar\xed')
        try:
            self.assertEqual(
                b.get_or_delegate('toupper', u'foobar\xed', 'item1'),
                None
            )
            # consume methods below another method has the lock, so assume
            # it will handle the request, and returns `None`
            self.assertEqual(
                b.consume('toupper', u'foobar\xed'),
                (None, None)
            )
        finally:
            b._config.cache.release('toupper', u'foobar\xed')

    def test_buggy_callback(self):
        b = TestToUpper._backache()
        b._config.callbacks.default = self._buggy_callback
        self.assertEqual(
            b.get_or_delegate('toupper', u'foobar\xed', 'item1'),
            None
        )
        with self.assertRaises(Exception) as exc:
            b.consume('toupper', u'foobar\xed')
        self.assertEqual(
            exc.exception.message,
            'Ooops, I forgot zzzat'
        )
        # ensure cache is properly filled
        self.assertEqual(b._config.cache.get('toupper', u'foobar\xed')[1],
                         u'FOOBAR\xcd')

    def test_invalid_operation(self):
        b = TestToUpper._backache()

        def oops(uri, context):
            raise Exception("Buggy operation")
        b._config.operations['buggy-operation'] = oops
        self.assertEqual(
            b.get_or_delegate('buggy-operation', u'foobar\xed', 'item1'),
            None
        )
        with self.assertRaises(Exception) as exc:
            b.consume('buggy-operation', u'foobar\xed')
        self.assertEqual(
            exc.exception.message,
            'Buggy operation'
        )
        self.assertEqual(
            b._config.cache.get('toupper', u'foobar\xed'),
            (None, None)
        )

    def test_redis_pop_error(self):
        b = TestToUpper._backache()
        # simulate failure of the `pop` operation
        b._config.resource.pop = mock.MagicMock(side_effect=KeyError('pika'))
        b.get_or_delegate('toupper', u'foobar\xed', 'item1')
        with self.assertRaises(KeyError) as exc:
            b.consume('toupper', u'foobar\xed')
        self.assertEqual(exc.exception.message, 'pika')
        # ensure there is no lock left behind
        self.assertEqual(
            b._config.cache.get('toupper', u'foobar\xed'),
            (None, None)
        )

    @classmethod
    def _buggy_callback(cls, uri, items):
        raise Exception("Ooops, I forgot zzzat")

    @classmethod
    def _callback(cls, result, cb_args):
        result = {'result': result, 'cb_args': set(cb_args)}
        cls._cb_calls.append(result)
        return result

if __name__ == '__main__':
    unittest.main()
