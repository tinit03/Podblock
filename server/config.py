import os


class Config:
    """Application Configuration Class"""
    UPLOAD_FOLDER = './uploads'
    CACHE_TYPE = 'redis'
    CACHE_REDIS_HOST = 'redis'
    CACHE_REDIS_PORT = 6379
    CACHE_REDIS_DB = 0
    REDIS_URL = "redis://redis:6379/0"

    CELERY_BROKER_URL = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND = "redis://redis:6379/0"
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_ACCEPT_CONTENT = ['json', 'json']
    CELERY_TIMEZONE = 'UTC'
    CELERY_ENABLE_UTC = True
