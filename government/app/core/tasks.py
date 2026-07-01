from celery import shared_task

from .utils import CleanUpData


@shared_task(name="Clean up old tokens and nonces")
def clean_up_old_tokens_and_nonces():
    CleanUpData().clean()
