# Backache

[![PyPI version](https://badge.fury.io/py/backache.svg)](http://badge.fury.io/py/backache)
[![Build Status](https://travis-ci.org/cogniteev/backache.svg)](https://travis-ci.org/cogniteev/backache)
[![Coverage Status](https://coveralls.io/repos/cogniteev/backache/badge.svg?branch=master&service=github)](https://coveralls.io/github/cogniteev/backache?branch=master)
[![Code Climate](https://codeclimate.com/github/cogniteev/backache/badges/gpa.svg)](https://codeclimate.com/github/cogniteev/backache)
[![Code Health](https://landscape.io/github/cogniteev/backache/master/landscape.svg?style=plastic)](https://landscape.io/github/cogniteev/backache/master)

Backache is a Python module providing an asynchronous URI processing library.
Processing of your resources is made once and then stored in a cache, to speed
up identical queries in the future.

The processing itself is made asynchronously, and your consumers are spawned
when awaited processing is finished.

Default backends:

* Asynchronous processing: [Celery](http://celery.readthedocs.org/)
* Document cache: [MongoDB](https://www.mongodb.org/)
* Processing queue: [Redis](http://redis.io/)

# How it works

Assuming that you use RabbitMQ as message broker for Celery, here is what
the processing of `key` with `op` operation looks like. `cb_args` are
arguments that will be given to the callback dealing with the
processing result.

## Cache miss
Here is what happens when the result of the `op` operation for the given
`key` is not yet in the cache.
![cache miss sequence diagram](docs/cache-miss.png)

With the `task_id` returned, the client is able to wait for the end of the
callback processing.

## Cache hit
The following diagram describes what happens when processing of `key` by the
`op` operation already in the cache.

![cache hit sequence diagram](docs/cache-hit.png)

In this case, processing result is not sent to a delayed task but returned
immediately to the client. Why doing that? Because in many situations,
the client very well knows what to do with it, and in most situations, delay
the result processing is less efficient.

## Twice for the same price

According to the kind of data you deal with, the time window during which
two clients want to process an unknown resource is more or less large.
In such situation, Backache tries to bulk the two requests in one single
callback operation.

![bulk sequence diagram](docs/bulk.png)

The situation is quite idealistic, but is more an optimization than a real
breakthrough. But it raises a question:

**Why isn't the operation executed inside the lock?**

And this leads to the next *missing* section ... URI redirections.


## API

### Functions and tasks prototypes

#### Operations

A Backache operation must have the following signature:

```python
def my_operation(uri, context, **kwargs):
    """`my_operation` processor

    :param basestring uri:
      Unique Resource Identifier to compute

    :param backache.OperationContext context:
      processing context. If backache is running in Celery mode, then
      an instance of `backache.AsyncOperationContext` is given.

    :param dict kwargs:
      Optional argument, that can be specified when retrying a task.

    :return:
      operation result. Instance must be serializable with *pickle*.
    :rtype: `dict` is advised.
    """
```

#### Operation callback

An operation callback may be a `Celery` task, with the following signature:

```python
@celery.task(name='backache.callback.my_operation')
def my_operation_callback(result):
    """Processing result of one backache operation

    :param tuple result:
      tuple of 2 elements:
      - first element is the operation result
      - second element is a list of callback arguments, specified either
        in `CeleryCache.get_or_delegate` or `CeleryCache.bulk_get_or_delegate`
    """
```

#### Cache hits callbacks

Those are callable objects given to `backache.Backache#bulk_get_or_delegate`
member method. They are used to consume results for which there are been
a cache hit, to avoid unnecessary computation in the future.

This kind of callable must take one `dict` in parameter. Every key in a
pair *(operation, uri)*, and values are a `dict` made of the following keys:

* `cb_args`: specified in input of the `bulk_get_or_delegate` member method.
* `result`: cache hit result

#### Quarantine tasks

Celery tasks consuming the Backache *quarantine* queue must have the
following signature:

```python
@celery.task(name='backache.quarantine-consumer')
def quarantine_consumer(operation, uri, exc):
    """Consume tasks moved in the Backache quarantine queue

    :param basestring operation:
      the operation name that failed

    :param basestring uri:
      URI for which the processing failed

    :param Exception exc:
      The exception raised. Can be an instance of
      `ProcessingInQuarantineException` if canceled by the task explicitly,
      providing the `op_kwargs` parameters of the failed task, an instance
      of `Exception` otherwise.
    """
```

### Error handling

A processing task is given a `context` instance that allows the task
to manage itself.

#### Operation retry
A task can retry itself in the future via the `retry` member method
of the given *context*.
The task can specify the `kwargs` arguments of the retried task.

For instance, this can be used to know how many times the task
has been retried. (see example below)

#### Operation failure

A processing tasks can also cancel itself definitely via the `quarantine`
member method of the given context. In such event, the
task is moved in a custom `quarantine` queue (by default *backache-queue*).
Note that the `quarantine` member methods accepts `kwargs` argument,
available in tasks pushed in the *backache-queue*.

This can be used to push errors, status code, ...


Note: If a processing task throws an `Exception`, it is immediately moved in
the *quarantine* queue.

#### Example:
The operation task below demonstrate how a task can retry itself no more
than 3 times.

```python
def my_operation(uri, context, attempt=1):
    try:
        result = None
        # do things...
        return result
    except:
        if attempt != 3:
            raise context.retry(countdown=5, attempt=attempt + 1)
        raise context.quarantine()
```

# Installation

```shell
$ pip install backache
```

# Tests

Use `tox` to run the tests-suite on every supported platforms:

```shell
# Install and load virtualenv
$ pip install virtualenv
$ virtualenv .env
$ . .env/bin/activate
# Install tox
$ pip install tox
# Run the test suites
$ tox
```

The test-suite requires MongoDB 2.6, Redis, Celery, and RabbitMQ to be up
and running.

Take a look at the [.travis.yml](.travis.yml) configuration to get the proper
`celery` command line.

# License

Backache is licensed under the Apache License, Version 2.0.
See [LICENSE](LICENSE) file for full license text.
