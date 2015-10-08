import sys
import time
import hashlib

from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError

from errors import (
    ResourceAlreadyExists,
    ResourceLocked,
    ResourceNotLocked,
    UnknownResource,
)


class ResourceCache(object):  # pragma: no cover
    def lock(self, operation, uri):
        """ Create incomplete document to notify the resource is locked.

        :param: basestring operation:
          operation to apply on the resource
        :param: basestring uri:
          unique resource identifier

        :return: document identifier
        :rtype: unicode

        :raises ResourceLockedError:
          if resource is already locked
        :raises ResourceAlreadyExists:
          if the resource is a valid document
        """
        raise NotImplementedError()

    def get(self, operation, uri):
        """ Get payload associated to a pair (operation, uri)
        :return: pair (uri, payload)
          - uri: the real URI holding the payload if it exists,
           `None` otherwise
          - payload: the payload if it exists, `None` otherwise
        """
        raise NotImplementedError()

    def fill(self, operation, uri, content, redirects=None):
        """ Fill an existing document with the real content to cache.

        There is no need to know the payload to add redirect URIs
        to an existing (locked) document. In this case, set `content`
        parameter to `None`

        :param: basestring uri:
          document cache identifier
        :param: object content:
          content to cache
        :param list of basestring redirects:
          associated URI redirects
        :raises ResourceAlreadyExists:
          if document is already filled
        :raises ResourceNotLocked:
          if document is not currently locked
        """
        raise NotImplementedError()

    def release(self, operation, uri):
        """ Remove lock
        :raises: ResourceNotLocked:
          when referenced document is not locked or does not exist.
        """
        raise NotImplementedError()

    def delete_lock(self, operation, uri):
        """ Delete a locked document """
        raise NotImplementedError()


class MongoCache(ResourceCache):
    LOCK_STATUS = 'lock'
    CACHE_STATUS = 'cache'

    def __init__(self, **kwargs):
        connection_params = dict(kwargs.get('connection_params'))
        connection_params.pop('db', None)
        client = MongoClient(**connection_params)
        self._db = client[kwargs['db']]
        self._collection = self._db[kwargs.get('collection', 'backache')]
        self._collection.ensure_index(
            [
                ('hash', ASCENDING),
                ('operation', ASCENDING),
            ],
            name='_backache_hash_op',
            unique=True
        )
        self._collection.ensure_index(
            [
                ('operation', ASCENDING),
                ('hashed_redirects', ASCENDING),
            ],
            name='_backache_redirects_op',
            unique=True
        )

    def clear(self):
        self._collection.drop()
        self._collection.drop_indexes()

    def lock(self, operation, uri):
        return self._lock(operation, uri, MongoCache.LOCK_STATUS)

    def _lock(self, operation, uri, status):
        try:
            return self._collection.update({
                'hash': self._hash(uri),
                'operation': operation,
                'status': MongoCache.CACHE_STATUS,
                'uri': uri,
            }, {
                '$set': {
                    'status': status,
                }
            }, upsert=True)

        except DuplicateKeyError:
            raise ResourceLocked(operation, uri), None, sys.exc_info()[2]

    def release(self, operation, uri):
        result = self._collection.update({
            'operation': operation,
            'hash': self._hash(uri),
            'status': MongoCache.LOCK_STATUS,
        }, {
            '$set': {
                'status': MongoCache.CACHE_STATUS,
            },
        })
        if result['n'] != 1:
            raise ResourceNotLocked(operation, uri), None, sys.exc_info()[2]

    def delete_lock(self, operation, uri):
        result = self._collection.remove({
            'operation': operation,
            'status': MongoCache.LOCK_STATUS,
            'hash': self._hash(uri),
        })
        if result['n'] == 0:
            raise ResourceNotLocked(operation, uri), None, sys.exc_info()[2]

    def get(self, operation, uri):
        for op in [self._get_by_uri, self._get_by_redirects]:
            doc = op(operation, self._hash(uri))
            if doc is not None:
                return doc['uri'], doc.get('cache')
        return None, None

    def _get_by_uri(self, operation, uri_hash):
        return self._collection.find_and_modify(
            {
                'operation': operation,
                'status': MongoCache.CACHE_STATUS,
                'hash': uri_hash,
            },
            {
                '$push': {
                    'direct_hits': self._now_ms(),
                },
            },
        )

    def _get_by_redirects(self, operation, uri_hash):
        return self._collection.find_and_modify(
            {
                'operation': operation,
                'status': MongoCache.CACHE_STATUS,
                'hashed_redirects': uri_hash,
            },
            {
                '$push': {
                    'redirect_hits': self._now_ms(),
                },
            },
        )

    def fill(self, operation, uri, content, redirects=None):
        redirects = redirects or []
        redirects.append(uri)
        update_operations = {}
        if content is not None:
            update_operations.setdefault('$set', {})['cache'] = content
        update_operations.update({
            '$addToSet': {
                'hashed_redirects': {
                    '$each': [
                        self._hash(redirect) for redirect in redirects
                    ],
                },
                'redirects': {
                    '$each': redirects
                }
            },
        })
        result = self._collection.find_and_modify(
            {
                'operation': operation,
                'hash': self._hash(uri),
                'status': MongoCache.LOCK_STATUS,
            },
            update_operations,
            full_response=True
        )
        if result['value'] == None:
            cache = self._collection.find({
                'operation': operation,
                'hash': self._hash(uri),
            })
            try:
                error_args = {'op': operation, 'uri': uri}
                if cache.count() == 0:
                    raise UnknownResource(operation, uri)
                elif cache.count() != 1:
                    message = u"Unexpected matched results while filling " \
                              "document: {op}/{uri}, matched: " \
                              u"{count}"
                    raise Exception(message.format(
                        count=cache.count(),
                        **error_args)
                    )
                else:
                    document = cache[0]
                    if document['status'] == MongoCache.CACHE_STATUS:
                        raise ResourceAlreadyExists(operation, uri)
                    else:
                        message = u"Could not set document content: {op}/{uri}"
                        raise Exception(message.format(**error_args))
            finally:
                cache.close()

    def _hash(self, uri):
        return hashlib.sha256(uri.encode('utf8')).hexdigest()

    @classmethod
    def _now_ms(cls):
        return int(round(time.time() * 1000))
