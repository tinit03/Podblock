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

    broker_url = f'{BASE_REDIS}/1'
    result_backend = f'{BASE_REDIS}/2'
    task_serializer = 'json'
    result_serializer = 'json'
    accept_content = ['json']

    task_queues = (
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

    task_default_queue = "background"
    task_default_exchange = "background"
    task_default_routing_key = "background.default"
