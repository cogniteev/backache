import unittest

from pymongo import MongoClient

from backache.cache import MongoCache
from backache.errors import (
    ResourceAlreadyExists,
    ResourceLocked,
    ResourceNotLocked,
    UnknownResource,
)


class MongoTest(unittest.TestCase):
    OPTIONS = {
        'connection_params': {
            'host': 'localhost',
        },
        'db': 'backache',
        'collection': 'backache',
    }

    @classmethod
    def setUpClass(cls):
        client = MongoClient(**cls.OPTIONS['connection_params'])
        db = client[cls.OPTIONS['db']]
        cls.collection = db[cls.OPTIONS['collection']]

    def setUp(self):
        self.collection.drop()

    def test_init(self):
        MongoCache(**self.OPTIONS)
        indices = list(self.collection.index_information())
        self.assertEqual(len(indices), 3)
        self.assertIn('_backache_uri_op', indices)
        self.assertIn('_backache_redirects', indices)

    def test_lock(self):
        cache = MongoCache(**self.OPTIONS)
        cache.lock('foo', 'bar')
        try:
            with self.assertRaises(ResourceLocked) as exc:
                cache.lock('foo', 'bar')
            self.assertEqual(exc.exception.operation, 'foo')
            self.assertEqual(exc.exception.uri, 'bar')
        finally:
            cache.release('foo', 'bar')

    def test_bad_unlock(self):
        cache = MongoCache(**self.OPTIONS)
        with self.assertRaises(ResourceNotLocked) as exc:
            cache.release('foo', 'bar')
        self.assertEqual(exc.exception.operation, 'foo')
        self.assertEqual(exc.exception.uri, 'bar')

    def test_fill_unknown_resource(self):
        cache = MongoCache(**self.OPTIONS)
        with self.assertRaises(UnknownResource) as exc:
            cache.fill('foo', 'bar', 'some_content', [])
        self.assertEqual(exc.exception.operation, 'foo')
        self.assertEqual(exc.exception.uri, 'bar')

    def test_fill_existing_resource(self):
        cache = MongoCache(**self.OPTIONS)
        self.collection.insert({
            'operation': 'foo',
            'uri': 'bar',
            'status': MongoCache.CACHE_STATUS,
        })
        with self.assertRaises(ResourceAlreadyExists) as exc:
            cache.fill('foo', 'bar', 'some_content', [])
        self.assertEqual(exc.exception.operation, 'foo')
        self.assertEqual(exc.exception.uri, 'bar')

    def test_fill_redirects(self):
        cache = MongoCache(**self.OPTIONS)
        try:
            cache.lock('foo', 'bar')
            cache.fill('foo', 'bar', 'content', ['kikoo', 'lol'])
        finally:
            cache.release('foo', 'bar')
        self.assertEqual(cache.get('foo', 'lol')[1], 'content')

        # Now let's add a redirect
        try:
            cache.lock('foo', 'bar')
            cache.fill('foo', 'bar', None, ['bonjour'])
        finally:
            cache.release('foo', 'bar')
        self.assertEqual(cache.get('foo', 'bonjour')[1], 'content')
        self.assertEqual(cache.get('foo', 'lol')[1], 'content')

    def test_indices(self):
        cache = MongoCache(**self.OPTIONS)
        for op in ['op1', 'op2']:
            for key in ['key1', 'key2']:
                try:
                    cache.lock(op, key)
                    cache.fill(op, key, 'content')
                finally:
                    cache.release(op, key)

    def _get_document(self, cache, operation, uri):
        document = cache._collection.find_one({
            'operation': 'foo',
            'uri': 'bar'
        })
        self.assertIsNotNone(document)
        return document

    def test_counters(self):
        cache = MongoCache(**self.OPTIONS)
        try:
            cache.lock('foo', 'bar')
            cache.fill('foo', 'bar', 'content', ['kikoo', 'lol'])
        finally:
            cache.release('foo', 'bar')
        document = self._get_document(cache, 'foo', 'bar')
        self.assertFalse('direct_hits' in document)
        self.assertFalse('redirects_hits' in document)
        self.assertEqual(
            cache.get('foo', 'bar'),
            ('bar', 'content')
        )
        document = self._get_document(cache, 'foo', 'bar')
        self.assertTrue(len(document['direct_hits']), 1)
        self.assertFalse('redirects_hits' in document)
        self.assertEqual(
            cache.get('foo', 'kikoo'),
            ('bar', 'content')
        )
        document = self._get_document(cache, 'foo', 'bar')
        self.assertTrue(len(document['direct_hits']), 1)
        self.assertTrue(len(document['redirect_hits']), 1)


if __name__ == '__main__':
    unittest.main()
