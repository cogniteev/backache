from . core import Backache, OperationContext
from . utils import nameddict

DEFAULT_QUEUE = 'backache'
DEFAULT_QUARANTINE_QUEUE = 'backache-quarantine'


class ProcessingRetryException(Exception):
    """Raised by an operation task, it tells backache to retry
    the processing task later.
    """
    def __init__(self, countdown=None, **kwargs):
        """
        :param int countdown:
          Time in seconds to delay the retry
        :param dict op_kwargs:
          Arguments given to the next processing task
        """
        super(ProcessingRetryException, self).__init__()
        self.countdown = countdown
        self.op_kwargs = kwargs


class ProcessingInQuarantineException(Exception):
    """Raised by an operation task, it tells backache to move this failing
    task in a dedicated task used for quarantine
    """
    def __init__(self, op_kwargs=None, **kwargs):
        """
        :param dict op_kwargs:
          `kwargs` arguments given the task that raised this exception.

        :param dict kwargs:
          optional `dict` given to the quarantine task. It may provide
          additional information, useful to investigate the issue like
          status_code, errors, ...
        """
        super(ProcessingInQuarantineException, self).__init__()
        self.op_kwargs = op_kwargs
        self.kwargs = kwargs


class CeleryCache(Backache):
    def __init__(self, **kwargs):
        self.__super = super(CeleryCache, self)
        self.__super.__init__(**kwargs)
        self._config.celery = kwargs.get('celery', {})
        self._tasks = nameddict(kwargs.get('celery_tasks'))

    def get_or_delegate(self, operation, uri, *cb_args):
        """ Retrieve result of the specified operation for the given URI
        or trigger the processing asynchronously.

        :return:
          cached value if available, a Celery `TaskResult` otherwise.
        """
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
        misses, errors = self.__super.bulk_get_or_delegate(
            commands, cache_hits_cb
        )
        tasks = []
        for operation, uri, appended in misses:
            if not appended:
                tasks.append(self._delegate_async(operation, uri))
        for task_error in errors:
            if isinstance(task_error.exc, ProcessingRetryException):
                tasks.append(self._delegate_async(
                    task_error.operation,
                    task_error.uri,
                    countdown=task_error.exc.countdown,
                    op_kwargs=task_error.exc.op_kwargs
                ))
            else:
                self.move_in_quarantine(
                    task_error.operation,
                    task_error.uri,
                    task_error.exc
                )
        return tasks

    def _delegate_async(self, operation, uri, countdown=None, op_kwargs=None):
        """ Asynchronously process the operation and provide the result to
        the operation callback.
        """
        from celery import chain
        return chain(
            self._tasks.consume.subtask(
                args=(operation, uri),
                kwargs={'op_kwargs': op_kwargs},
                queue=self._celery_queue('consume', operation),
                countdown=countdown
            ),
            self._processing_callback(operation, uri)
        )()

    def _processing_callback(self, operation, uri):
        """ Internally provide the proper callback.
        """
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

    def _fire_callback(self, operation, uri, cached_doc, cb_args, **kwargs):
        """ Override parent member method
        The callback method is NOT directly called here. This code is
        executed in a Celery chain, and the next task is the callback,
        that expects the 2 arguments returned by this method.

        :returns: 2 first arguments of the Celery `callback` task
        """
        del kwargs  # unused
        return cached_doc, cb_args

    def move_in_quarantine(self, operation, uri, exc):
        if self._tasks.quarantine is not None:
            queue = self._config.celery.get(
                'quarantine_queue',
                DEFAULT_QUARANTINE_QUEUE
            )
            cb_args = self._config.resource.pop(operation, uri)
            return self._tasks.quarantine.apply_async(
                args=(operation, uri, cb_args, exc),
                queue=queue
            )

    def _context(self, **kwargs):
        return AsyncOperationContext(**kwargs)


class AsyncOperationContext(OperationContext):
    """operation context given to processing task in Celery context.
    Tasks have the ability:
    - to retry themselves later in the future
    - set the task status to failure, and the task in moved in a quarantine
    queue.
    """
    def retry(self, **kwargs):
        """Ask the task to be retried later in the future.

        :param dict kwargs:
          If present, the `countdown` attribute specifies the number of
          seconds the task should execute in the future. Defaults to
          immediate execution.
          Other attributes will be given to the retried task as `kwargs`
          argument.

        :raises ProcessingRetryException:
          That must not be catched by the processing task
        """
        raise ProcessingRetryException(**kwargs)

    def quarantine(self, **kwargs):
        """Cancel this processing task and move it to a quarantine queue.

        :param dict kwargs:
          optional `dict` given to the quarantine task. It may provide
          additional information, useful to investigate the issue like
          status_code, errors, ...

        :raises ProcessingInQuarantineException:
          That must be catched by the processing task
        """
        raise ProcessingInQuarantineException(self._op_kwargs, **kwargs)


def celerize(celery_app, **config):
    """Build a `Backache` instanced using Celery to perform
    asynchronous processing.
    """
    backache = None

    @celery_app.task(name='backache.consume', bind=True)
    def backache_consume(task, operation, uri, op_kwargs=None):
        result, cb_args = None, None
        try:
            result, cb_args = backache.consume(
                operation, uri, op_kwargs=op_kwargs
            )
        except ProcessingRetryException as e:
            raise task.retry(  # pragma NOCOVER
                countdown=e.countdown,
                kwargs={'op_kwargs': e.op_kwargs}
            )
        except ProcessingInQuarantineException as e:  # pragma: no cover
            backache.move_in_quarantine(operation, uri, e)
        if cb_args is not None and not any(cb_args):  # pragma: no cover
            # do not call the callback
            task.request.callbacks = None
        return result, cb_args

    @celery_app.task(name='backache.callback')
    def backache_callback(args, operation, uri):
        cached_doc, cb_args = args
        _super = super(CeleryCache, backache)
        return _super._fire_callback(operation, uri, cached_doc, cb_args, True)

    config['celery_tasks'] = {
        'consume': backache_consume,
        'callback': backache_callback,
        'quarantine': config['celery'].get('quarantine_task'),
    }

    backache = CeleryCache(**config)
    return backache
