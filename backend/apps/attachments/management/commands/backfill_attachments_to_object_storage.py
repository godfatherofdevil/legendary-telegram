from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ...models import Attachment
from ...storage import (
    LocalFilesystemAttachmentStorage,
    attachment_storage_root,
    get_attachment_storage,
)


class Command(BaseCommand):
    help = "Copy legacy filesystem attachment blobs into the configured object storage backend."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--source-root",
            default=str(attachment_storage_root()),
            help="Filesystem root containing legacy attachment blobs.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report pending work without uploading objects.",
        )

    def handle(self, *args, **options) -> None:
        storage = get_attachment_storage()
        if self._is_filesystem_storage(storage):
            raise CommandError(
                "backfill_attachments_to_object_storage requires ATTACHMENTS_STORAGE_BACKEND=s3."
            )

        source_root = Path(options["source_root"]).resolve()
        dry_run = options["dry_run"]
        stats = {
            "copied": 0,
            "skipped_existing": 0,
            "missing_source": 0,
            "size_mismatch": 0,
            "failed": 0,
        }

        for attachment in Attachment.objects.order_by("created_at", "id").iterator():
            source_path = source_root / attachment.storage_key
            source_exists = source_path.exists()

            if storage.exists(storage_key=attachment.storage_key):
                stats["skipped_existing"] += 1
                self.stdout.write(f"SKIP existing {attachment.id} {attachment.storage_key}")
                continue

            if not source_exists:
                stats["missing_source"] += 1
                self.stdout.write(f"MISSING {attachment.id} {source_path}")
                continue

            source_size = source_path.stat().st_size
            if source_size != attachment.size_bytes:
                stats["size_mismatch"] += 1
                self.stdout.write(
                    "SIZE_MISMATCH "
                    f"{attachment.id} expected={attachment.size_bytes} actual={source_size}"
                )
                continue

            if dry_run:
                stats["copied"] += 1
                self.stdout.write(f"DRY_RUN copy {attachment.id} {attachment.storage_key}")
                continue

            try:
                storage.upload_from_path(
                    storage_key=attachment.storage_key,
                    source_path=source_path,
                    content_type=attachment.content_type,
                    original_filename=attachment.original_filename,
                )
                copied_size = storage.size(storage_key=attachment.storage_key)
            except Exception as exc:
                stats["failed"] += 1
                self.stdout.write(f"FAILED {attachment.id} {exc}")
                continue

            if copied_size != source_size:
                storage.delete(storage_key=attachment.storage_key)
                stats["failed"] += 1
                self.stdout.write(
                    f"FAILED {attachment.id} copied_size={copied_size} expected={source_size}"
                )
                continue

            stats["copied"] += 1
            self.stdout.write(f"COPIED {attachment.id} {attachment.storage_key}")

        self.stdout.write(
            self.style.SUCCESS(
                "Backfill summary: "
                + ", ".join(f"{key}={value}" for key, value in stats.items())
            )
        )

    def _is_filesystem_storage(self, storage) -> bool:
        return isinstance(storage, LocalFilesystemAttachmentStorage)
