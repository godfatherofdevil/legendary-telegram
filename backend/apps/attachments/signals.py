from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Attachment
from .services import delete_attachment_file


@receiver(post_delete, sender=Attachment)
def delete_attachment_storage_on_row_delete(sender, instance: Attachment, **kwargs) -> None:
    delete_attachment_file(storage_key=instance.storage_key)
