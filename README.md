# Backache

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

The test-suite requires MongoDB 2.6 and Redis with Sentinel to be up
and running.

# License

Backache is licensed under the Apache License, Version 2.0.
See [LICENSE](LICENSE) file for full license text.
