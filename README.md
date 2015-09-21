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

# Installation

```shell
$ pip install backache
```

# Tests

Use `tox` to run the tests-suite on every supported platform:

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

The test-suite requires MongoDB 2.6 and Redis to be up and running.

# License

Backache is licensed under the Apache License, Version 2.0.
See [LICENSE](LICENSE) file for full license text.
