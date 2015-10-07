""" Utility stuff to provide unit-tests backache results
built by Celery workers
"""

from celery import Celery
from backache.utils import nameddict


celery = Celery()


class TasksResultsCollector:

    processing_callback_results = []
    bulk_cache_hit_results = []
    quarantine_tasks = []

    @classmethod
    def add_processing_callback(cls, result, cb_args):
        cls.processing_callback_results.append({
            'result': result,
            'cb_args': cb_args,
        })

    @classmethod
    def add_bulk_cache_hit_results(cls, results):
        cls.bulk_cache_hit_results.append(results)

    @classmethod
    def add_quarantine_task(cls, operation, uri, cb_args, exc):
        cls.quarantine_tasks.append({
            'operation': operation,
            'uri': uri,
            'cb_args': cb_args,
            'exc': exc,
        })

    @classmethod
    def clear(cls):
        cls.processing_callback_results = []
        cls.bulk_cache_hit_results = []
        cls.quarantine_tasks = []


@celery.task(name='backache.ut.get_processing_callbacks')
def get_processing_callbacks():
    return TasksResultsCollector.processing_callback_results


@celery.task(name='backache.ut.get_bulk_cache_hits_results')
def get_bulk_cache_hits_results():
    return TasksResultsCollector.bulk_cache_hit_results


@celery.task(name='backache.ut.get_quarantine_tasks')
def get_quarantine_tasks():
    return TasksResultsCollector.quarantine_tasks


@celery.task(name='backache.ut.clear_results')
def clear_results():
    return TasksResultsCollector.clear()


def get_tasks_results_collector_tasks():
    return nameddict({
        'processing_callbacks': get_processing_callbacks,
        'bulk_cache_hit_results': get_bulk_cache_hits_results,
        'quarantine_tasks': get_quarantine_tasks,
        'clear_results': clear_results,
    })
