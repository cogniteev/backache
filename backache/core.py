from contextlib import contextmanager

from .cache import MongoCache
from .resource import RedisStore
from .errors import ResourceLocked
from .utils import nameddict


__all__ = [
    'Backache',
]


class OperationContext(object):
    def __init__(self, operation=None, cache=None):
        self.__operation = operation
        self.__cache = cache
        self._match_uri = None
        self._redirects = []

    def get_or_add_redirect(self, uri):
        real_uri, result = self.__cache.get(self.__operation, uri)
        if result is not None:
            self._match_uri = real_uri
        else:
            self._redirects.append(uri)
        return result

    def _deliberate(self, uri, cached_doc):
        if self._match_uri:
            update_uri = self._match_uri
            cached_doc = None
        else:
            if any(self._redirects):
                # last asked is final URI
                update_uri = self._redirects.pop(-1)
            else:
                update_uri = uri

        if update_uri != uri:
            if uri not in self._redirects:
                self._redirects.append(uri)
        return update_uri, cached_doc, self._redirects


class Backache(object):
    def __init__(self, **kwargs):
        cache_config = kwargs.get('cache', {})
        resource_cls = kwargs.get('resource_cls', RedisStore)
        resource_config = kwargs.get('resource', {})
        callbacks = kwargs.get('callbacks', {})
        callbacks.setdefault('default', None)
        callbacks.setdefault('operations', {})
        self._config = nameddict({
            'cache': kwargs.get('cache_cls', MongoCache)(**cache_config),
            'resource': resource_cls(**resource_config),
            'operations': dict(kwargs.get('operations', {})),
            'callbacks': callbacks,
        })

    def get_or_delegate(self, operation, uri, *cb_args):
        _, cached_doc = self._cached_document(operation, uri)
        if cached_doc:
            return cached_doc
        else:
            self._config.resource.add(operation, uri, *cb_args)

    def _operation_callback(self, operation):
        op_cbs = self._config.callbacks.operations
        cb = op_cbs.get(operation, self._config.callbacks.default)
        return cb

    def consume(self, operation, uri, delay=None):
        real_uri, cached_doc = self._cached_document(operation, uri)

        if cached_doc:
            cb_args = self._config.resource.pop(operation, uri)
            return self._fire_callback(operation, uri, cached_doc,
                                       cb_args, delay)
        else:
            if self._config.resource.count(operation, uri) == 0:
                return
            cached_doc, context = self._process_operation(operation, uri)
            try:
                cb_args = self._update_cache(operation, uri,
                                             cached_doc, context)
            except ResourceLocked:
                # Another task put the lock, and will take care of
                # processing the job. Nothing to do here...
                return None
            return self._fire_callback(operation, uri, cached_doc,
                                       cb_args, delay)

    def _update_cache(self, operation, uri, cached_doc, context):
        resource_uri = uri
        uri, cached_doc, redirects = context._deliberate(uri, cached_doc)
        with self._lock_document(operation, uri, cached_doc, redirects):
            return self._config.resource.pop(operation, resource_uri)

    def _process_operation(self, operation, uri):
        func = self._config.operations.get(operation)
        if func is None:
            raise Exception("Unknown operation '{}'".format(operation))
        context = OperationContext(operation, self._config.cache)
        return func(uri, context), context

    @contextmanager
    def _lock_document(self, operation, uri, content, redirects):
        self._config.cache.lock(operation, uri)
        try:
            yield
        except:
            if self._config.cache.get(operation, uri)[1] == None:
                # no previous result
                self._config.cache.delete_lock(operation, uri)
            else:
                # release lock if something bad happened
                self._config.cache.release(operation, uri)
            raise
        else:
            # write document if no exception was raised in the context
            self._config.cache.fill(operation, uri, content, redirects)
            self._config.cache.release(operation, uri)

    def _fire_callback(self, operation, uri, cached_doc, cb_args, delay=False):
        callback = self._operation_callback(operation)
        delay = delay or (callback is not None)
        if delay and cb_args is not None and any(cb_args):
            return callback(cached_doc, cb_args)
        else:
            return cached_doc, cb_args

    def _cached_document(self, operation, uri):
        """
        :return: The Mongo document associated to the specified URL, `None`
        if document does not exist
        """
        return self._config.cache.get(operation, uri)
