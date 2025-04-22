import os

BASE_REDIS = os.environ.get("REDIS_URL", "redis://localhost:6379")

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
