import unittest
import hashlib

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
        self.assertIn('_backache_hash_op', indices)
        self.assertIn('_backache_redirects_op', indices)

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

    def test_delete_unknown_lock(self):
        cache = MongoCache(**self.OPTIONS)
        with self.assertRaises(ResourceNotLocked) as exc:
            cache.delete_lock('foo', 'bar')
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
            'hash': hashlib.sha256('bar'.decode('utf8')).hexdigest(),
            'status': MongoCache.CACHE_STATUS,
            'uri': 'bar',
        })
        with self.assertRaises(ResourceAlreadyExists) as exc:
            cache.fill('foo', 'bar', 'some_content', [])
        self.assertEqual(exc.exception.operation, 'foo')
        self.assertEqual(exc.exception.uri, 'bar')

    def test_fill_twice(self):
        cache = MongoCache(**self.OPTIONS)
        self._insert_foo_bar_doc(cache)
        self._insert_foo_bar_doc(cache, 'another_content')
        uri, content = cache.get('foo', 'bar')
        self.assertEqual(uri, 'bar')
        self.assertEqual(content, 'another_content')

    def test_fill_after_invalid_status(self):
        cache = MongoCache(**self.OPTIONS)
        cache._lock('foo', 'bar', -42)
        with self.assertRaises(Exception) as exc:
            cache.fill('foo', 'bar', 'content')
        self.assertEqual(
            exc.exception.message,
            'Could not set document content: foo/bar'
        )

    def test_fill_with_multiple_match(self):
        """Test fill method when there are 2 matching documents"""
        # indices need to be deactivated...
        cache = MongoCache(**self.OPTIONS)
        cache._collection.drop_indexes()
        uri = 'bar'
        for _ in range(2):
            cache._collection.insert({
                'hash': hashlib.sha256(uri.decode('utf8')).hexdigest(),
                'operation': 'foo',
                'status': MongoCache.CACHE_STATUS
            })
        with self.assertRaises(Exception) as exc:
            cache.fill('foo', 'bar', 'content')
        self.assertEqual(
            exc.exception.message,
            'Unexpected matched results while filling document: ' +
            'foo/bar, matched: 2'
        )

    def test_fill_redirects(self):
        cache = MongoCache(**self.OPTIONS)
        self._insert_foo_bar_doc(cache)
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
            'operation': operation,
            'hash': hashlib.sha256(uri.decode('utf8')).hexdigest()
        })
        self.assertIsNotNone(document)
        return document

    def _insert_foo_bar_doc(self, cache, content=None):
        content = content or 'content'
        try:
            cache.lock('foo', 'bar')
            cache.fill('foo', 'bar', content, ['kikoo', 'lol'])
        finally:
            cache.release('foo', 'bar')

    def test_counters(self):
        cache = MongoCache(**self.OPTIONS)
        self._insert_foo_bar_doc(cache)
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
