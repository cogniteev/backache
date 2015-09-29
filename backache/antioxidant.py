from . core import Backache
from . utils import nameddict

DEFAULT_QUEUE = 'backache'


class CeleryCache(Backache):
    def __init__(self, **kwargs):
        self.__super = super(CeleryCache, self)
        self.__super.__init__(**kwargs)
        self._config.celery = kwargs.get('celery', {})
        self._tasks = nameddict(kwargs.get('celery_tasks'))

    def get_or_delegate(self, operation, uri, *cb_args):
        cached_doc = self.__super.get_or_delegate(operation, uri, *cb_args)
        if cached_doc is not None:
            return cached_doc
        else:
            return self._delegate_async(operation, uri)

    def bulk_get_or_delegate(self, commands, cache_hits_cb):
        """ Behavior and signature are the same than
        `Backache:bulk_get_or_delegate`

        :return:
          task identifiers, asynchronously fired.
        :rtype:
          list of task identifier
        """
        misses = self.__super.bulk_get_or_delegate(commands, cache_hits_cb)
        tasks = []
        for operation, uri, appended in misses:
            if not appended:
                tasks.append(self._delegate_async(operation, uri))
        return tasks

    def _delegate_async(self, operation, uri):
        from celery import chain
        return chain(
            self._tasks.consume.subtask(
                (operation, uri),
                queue=self._celery_queue('consume', operation)
            ),
            self._processing_callback(operation, uri)
        )()

    def _processing_callback(self, operation, uri):
        from celery.local import Proxy
        from celery.canvas import Signature
        callback = self._operation_callback(operation)
        if isinstance(callback, Proxy):
            return callback.s()
        elif isinstance(callback, Signature):
            return callback
        else:
            return self._tasks.callback.subtask(
                (operation, uri),
                queue=self._celery_queue('callback', operation)
            )

    def _celery_queue(self, task_name, operation):
        tasks_config = self._config.celery.get('tasks', {})
        task_config = tasks_config.get(task_name, {})
        default_queue = self._config.celery.get('default_queue', DEFAULT_QUEUE)
        queue = task_config.get('queue', default_queue)
        return queue.format(operation=operation)

    def _fire_callback(self, operation, uri, cached_doc, cb_args, delay):
        """ Override parent member method
        The callback method is NOT directly called here. This code is
        executed in a Celery chain, and the next task is the callback,
        that expects the 2 arguments returned by this method.

        :returns: 2 first arguments of the Celery `callback` task
        """
        return cached_doc, cb_args


def celerize(celery_app, **config):
    backache = None

    @celery_app.task(name='backache.consume', bind=True)
    def backache_consume(task, operation, uri):
        result, cb_args = backache.consume(operation, uri)
        if cb_args is not None and not any(cb_args):
            # do not call the callback
            task.request.callbacks = None
        return result, cb_args

    @celery_app.task(name='backache.callback')
    def backache_callback(args, operation, uri):
        cached_doc, cb_args = args
        _super = super(CeleryCache, backache)
        return _super._fire_callback(operation, uri, cached_doc, cb_args)

    config['celery_tasks'] = {
        'consume': backache_consume,
        'callback': backache_callback,
    }
    backache = CeleryCache(**config)
    return backache
