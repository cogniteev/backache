from . celery_utils import celery  # NOQA
from . test_quarantine import TestQuarantine


TestQuarantine.setUpClass()
TestQuarantine._backache(with_celery=True)
