import sys
import time

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

    def fill(self, uri, content, redirects=None):
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
                ('uri', ASCENDING),
                ('operation', ASCENDING),
            ],
            name='_backache_uri_op',
            unique=True
        )
        self._collection.ensure_index(
            [
                ('operation', ASCENDING),
                ('redirects', ASCENDING),
            ],
            name='_backache_redirects',
            unique=True
        )

    def clear(self):
        self._collection.drop()

    def lock(self, operation, uri):
        try:
            return self._collection.update(
                {
                    'uri': uri,
                    'operation': operation,
                    'status': MongoCache.CACHE_STATUS,
                },
                {
                    '$set': {
                        'status': MongoCache.LOCK_STATUS,
                    }
                },
                upsert=True
            )

        except DuplicateKeyError:
            raise ResourceLocked(operation, uri), None, sys.exc_info()[2]

    def release(self, operation, uri):
        result = self._collection.update(
            {
                'operation': operation,
                'uri': uri,
                'status': MongoCache.LOCK_STATUS,
            }, {
                '$set': {
                    'status': MongoCache.CACHE_STATUS,
                },
            }
        )
        if result['n'] != 1:
            raise ResourceNotLocked(operation, uri), None, sys.exc_info()[2]

    def delete_lock(self, operation, uri):
        result = self._collection.remove({
            'operation': operation,
            'status': MongoCache.LOCK_STATUS,
            'uri': uri,
        })
        if result['n'] == 0:
            raise ResourceNotLocked(operation, uri), None, sys.exc_info()[2]

    def get(self, operation, uri):
        document = self._collection.find_and_modify(
            {
                'operation': operation,
                'status': MongoCache.CACHE_STATUS,
                'uri': uri
            },
            {
                '$push': {
                    'direct_hits': self._now_ms(),
                },
            },
        )
        if document is not None:
            return document['uri'], document.get('cache')
        document = self._collection.find_and_modify(
            {
                'operation': operation,
                'status': MongoCache.CACHE_STATUS,
                'redirects': uri
            },
            {
                '$push': {
                    'redirect_hits': self._now_ms(),
                },
            },
        )
        if document is not None:
            return document['uri'], document.get('cache')
        return None, None

    def fill(self, operation, uri, content, redirects=None):
        redirects = redirects or []
        redirects.append(uri)
        update_operations = {}
        if content is not None:
            update_operations.setdefault('$set', {})['cache'] = content
        if any(redirects):
            update_operations.update({
                '$addToSet': {
                    'redirects': {
                        '$each': redirects,
                    },
                },
            })
        result = self._collection.find_and_modify(
            {
                'operation': operation,
                'uri': uri,
                'status': MongoCache.LOCK_STATUS,
            },
            update_operations,
            full_response=True
        )
        if result['value'] == None:
            cache = self._collection.find({
                'operation': operation,
                'uri': uri,
            })
            try:
                error_args = {'op': operation, 'uri': uri}
                if cache.count() == 0:
                    raise UnknownResource(operation, uri)
                elif cache.count() != 1:
                    message = u"Unexpected matched results when filling " \
                              "document: {op}/{uri}, matched count: " \
                              "{matched_count}"
                    raise Exception(message.format(**error_args))
                else:
                    document = cache[0]
                    if document['status'] == MongoCache.CACHE_STATUS:
                        raise ResourceAlreadyExists(operation, uri)
                    else:
                        message = u"Could not set document content: {op}/{uri}"
                        raise Exception(message.format(**error_args))
            finally:
                cache.close()

    @classmethod
    def _now_ms(cls):
        return int(round(time.time() * 1000))
