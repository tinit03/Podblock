import os
from kombu import Queue

BASE_REDIS = os.environ.get("REDIS_URL", "redis://redis:6379")

class Config:
    """Application Configurations"""

    CACHE_TYPE = 'redis'
    CACHE_REDIS_HOST = 'redis'
    CACHE_REDIS_PORT = 6379
    CACHE_REDIS_DB = 0
    REDIS_URL = f'{BASE_REDIS}/0'

    CELERY_BROKER_URL = f'{BASE_REDIS}/1'
    CELERY_RESULT_BACKEND = f'{BASE_REDIS}/2'
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_ACCEPT_CONTENT = ['json']

    CELERY_TASK_QUEUES = (
        Queue(
            "stream",
            routing_key="stream.#",
            queue_arguments={"x-max-priority": 9},
        ),
        Queue(
            "background",
            routing_key="background.#",
            queue_arguments={"x-max-priority": 9},
        ),
    )

    CELERY_TASK_DEFAULT_QUEUE = "background"
    CELERY_TASK_DEFAULT_EXCHANGE = "background"
    CELERY_TASK_DEFAULT_ROUTING_KEY = "background.default"
