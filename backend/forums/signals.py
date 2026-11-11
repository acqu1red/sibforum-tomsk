import uuid

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import ContentRevision


@receiver([post_save, post_delete])
def update_public_revision(sender, instance, using, **kwargs):
    if sender._meta.app_label not in {'forums', 'voting'}:
        return
    if sender._meta.model_name in {'contentrevision', 'ballot', 'voteselection', 'voteattemptlog', 'voteresetlog'}:
        return
    def update():
        ContentRevision.objects.using(using).update_or_create(pk=1, defaults={'token': uuid.uuid4()})
    transaction.on_commit(update, using=using)
