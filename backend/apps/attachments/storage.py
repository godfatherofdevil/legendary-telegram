from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class AttachmentObjectNotFoundError(FileNotFoundError):
    pass


class AttachmentStorage:
    def put_uploaded_file(
        self, *, storage_key: str, uploaded_file, content_type: str, original_filename: str
    ) -> None:
        raise NotImplementedError

    def put_bytes(
        self, *, storage_key: str, data: bytes, content_type: str, original_filename: str
    ) -> None:
        raise NotImplementedError

    def upload_from_path(
        self, *, storage_key: str, source_path: Path, content_type: str, original_filename: str
    ) -> None:
        raise NotImplementedError

    def open(self, *, storage_key: str, byte_range: tuple[int, int] | None = None) -> BinaryIO:
        raise NotImplementedError

    def exists(self, *, storage_key: str) -> bool:
        raise NotImplementedError

    def size(self, *, storage_key: str) -> int:
        raise NotImplementedError

    def delete(self, *, storage_key: str) -> None:
        raise NotImplementedError

    def readiness_check(self) -> tuple[bool, dict]:
        raise NotImplementedError


def attachment_storage_root() -> Path:
    return Path(settings.MEDIA_ROOT) / settings.ATTACHMENTS_STORAGE_DIR


def attachment_absolute_path(storage_key: str) -> Path:
    return attachment_storage_root() / storage_key


class LocalFilesystemAttachmentStorage(AttachmentStorage):
    def put_uploaded_file(
        self, *, storage_key: str, uploaded_file, content_type: str, original_filename: str
    ) -> None:
        path = attachment_absolute_path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)

    def put_bytes(
        self, *, storage_key: str, data: bytes, content_type: str, original_filename: str
    ) -> None:
        path = attachment_absolute_path(storage_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def upload_from_path(
        self, *, storage_key: str, source_path: Path, content_type: str, original_filename: str
    ) -> None:
        self.put_bytes(
            storage_key=storage_key,
            data=source_path.read_bytes(),
            content_type=content_type,
            original_filename=original_filename,
        )

    def open(self, *, storage_key: str, byte_range: tuple[int, int] | None = None) -> BinaryIO:
        path = attachment_absolute_path(storage_key)
        if not path.exists():
            raise AttachmentObjectNotFoundError(storage_key)
        file_handle = path.open("rb")
        if byte_range is not None:
            start, _end = byte_range
            file_handle.seek(start)
        return file_handle

    def exists(self, *, storage_key: str) -> bool:
        return attachment_absolute_path(storage_key).exists()

    def size(self, *, storage_key: str) -> int:
        path = attachment_absolute_path(storage_key)
        if not path.exists():
            raise AttachmentObjectNotFoundError(storage_key)
        return path.stat().st_size

    def delete(self, *, storage_key: str) -> None:
        path = attachment_absolute_path(storage_key)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return

        parent = path.parent
        root = attachment_storage_root()
        while parent != root and parent.exists():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    def readiness_check(self) -> tuple[bool, dict]:
        storage_root = attachment_storage_root()
        return (
            storage_root.parent.exists(),
            {
                "attachment_storage": "ok" if storage_root.parent.exists() else "missing",
                "attachment_storage_root": str(storage_root),
            },
        )


def _build_s3_client():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=settings.ATTACHMENTS_S3_ENDPOINT_URL,
        aws_access_key_id=settings.ATTACHMENTS_S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.ATTACHMENTS_S3_SECRET_ACCESS_KEY,
        region_name=settings.ATTACHMENTS_S3_REGION,
        use_ssl=settings.ATTACHMENTS_S3_USE_SSL,
        verify=settings.ATTACHMENTS_S3_VERIFY_SSL,
        # MinIO in local Docker is exposed on a single endpoint, so bucket requests
        # must use path-style URLs like /uploads/... instead of uploads.minio:9000.
        config=Config(s3={"addressing_style": "path"}),
    )


class S3AttachmentStorage(AttachmentStorage):
    def __init__(self) -> None:
        if not settings.ATTACHMENTS_S3_ENDPOINT_URL:
            raise ImproperlyConfigured(
                "ATTACHMENTS_S3_ENDPOINT_URL must be configured for the s3 attachment backend."
            )
        if not settings.ATTACHMENTS_S3_BUCKET:
            raise ImproperlyConfigured(
                "ATTACHMENTS_S3_BUCKET must be configured for the s3 attachment backend."
            )

    @property
    def bucket_name(self) -> str:
        return settings.ATTACHMENTS_S3_BUCKET

    def _client(self):
        return _build_s3_client()

    def _extra_args(self, *, content_type: str, original_filename: str) -> dict:
        return {
            "ContentType": content_type,
            "Metadata": {"original_filename": original_filename},
        }

    def put_uploaded_file(
        self, *, storage_key: str, uploaded_file, content_type: str, original_filename: str
    ) -> None:
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
        self._client().upload_fileobj(
            uploaded_file,
            self.bucket_name,
            storage_key,
            ExtraArgs=self._extra_args(
                content_type=content_type,
                original_filename=original_filename,
            ),
        )

    def put_bytes(
        self, *, storage_key: str, data: bytes, content_type: str, original_filename: str
    ) -> None:
        self._client().put_object(
            Bucket=self.bucket_name,
            Key=storage_key,
            Body=data,
            **self._extra_args(content_type=content_type, original_filename=original_filename),
        )

    def upload_from_path(
        self, *, storage_key: str, source_path: Path, content_type: str, original_filename: str
    ) -> None:
        with source_path.open("rb") as source:
            self._client().upload_fileobj(
                source,
                self.bucket_name,
                storage_key,
                ExtraArgs=self._extra_args(
                    content_type=content_type,
                    original_filename=original_filename,
                ),
            )

    def open(self, *, storage_key: str, byte_range: tuple[int, int] | None = None) -> BinaryIO:
        extra_args = {}
        if byte_range is not None:
            start, end = byte_range
            extra_args["Range"] = f"bytes={start}-{end}"
        try:
            response = self._client().get_object(
                Bucket=self.bucket_name,
                Key=storage_key,
                **extra_args,
            )
        except Exception as exc:
            if _is_not_found_error(exc):
                raise AttachmentObjectNotFoundError(storage_key) from exc
            raise
        return response["Body"]

    def exists(self, *, storage_key: str) -> bool:
        try:
            self._client().head_object(Bucket=self.bucket_name, Key=storage_key)
        except Exception as exc:
            if _is_not_found_error(exc):
                return False
            raise
        return True

    def size(self, *, storage_key: str) -> int:
        try:
            response = self._client().head_object(Bucket=self.bucket_name, Key=storage_key)
        except Exception as exc:
            if _is_not_found_error(exc):
                raise AttachmentObjectNotFoundError(storage_key) from exc
            raise
        return int(response["ContentLength"])

    def delete(self, *, storage_key: str) -> None:
        self._client().delete_object(Bucket=self.bucket_name, Key=storage_key)

    def readiness_check(self) -> tuple[bool, dict]:
        client = self._client()
        try:
            client.head_bucket(Bucket=self.bucket_name)
        except Exception as exc:
            if _bucket_is_listed(client, self.bucket_name):
                return (
                    True,
                    {
                        "object_storage": "ok",
                        "object_storage_bucket": self.bucket_name,
                        "object_storage_endpoint": settings.ATTACHMENTS_S3_ENDPOINT_URL,
                    },
                )
            return (
                False,
                {
                    "object_storage": "error",
                    "object_storage_bucket": self.bucket_name,
                    "object_storage_endpoint": settings.ATTACHMENTS_S3_ENDPOINT_URL,
                    "object_storage_error": _describe_storage_error(exc),
                },
            )

        return (
            True,
            {
                "object_storage": "ok",
                "object_storage_bucket": self.bucket_name,
                "object_storage_endpoint": settings.ATTACHMENTS_S3_ENDPOINT_URL,
            },
        )


def _bucket_is_listed(client, bucket_name: str) -> bool:
    try:
        response = client.list_buckets()
    except Exception:
        return False

    buckets = response.get("Buckets", [])
    return any(bucket.get("Name") == bucket_name for bucket in buckets)


def _is_not_found_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    error = response.get("Error", {})
    return str(error.get("Code")) in {"404", "NoSuchKey", "NotFound"}


def _describe_storage_error(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        error = response.get("Error", {})
        code = error.get("Code")
        message = error.get("Message")
        if code and message:
            return f"{code}: {message}"
        if code:
            return str(code)
    return str(exc) or exc.__class__.__name__


def get_attachment_storage() -> AttachmentStorage:
    backend = settings.ATTACHMENTS_STORAGE_BACKEND
    if backend == "filesystem":
        return LocalFilesystemAttachmentStorage()
    if backend == "s3":
        return S3AttachmentStorage()
    raise ImproperlyConfigured(
        "ATTACHMENTS_STORAGE_BACKEND must be one of: filesystem, s3."
    )


def get_legacy_attachment_storage() -> LocalFilesystemAttachmentStorage | None:
    if settings.ATTACHMENTS_STORAGE_BACKEND != "s3":
        return None
    return LocalFilesystemAttachmentStorage()


def open_attachment_for_download(
    *, storage_key: str, byte_range: tuple[int, int] | None = None
) -> BinaryIO:
    storage = get_attachment_storage()
    try:
        return storage.open(storage_key=storage_key, byte_range=byte_range)
    except AttachmentObjectNotFoundError:
        legacy_storage = get_legacy_attachment_storage()
        if legacy_storage is None:
            raise
        return legacy_storage.open(storage_key=storage_key, byte_range=byte_range)


def delete_attachment_from_storage(*, storage_key: str) -> None:
    storage = get_attachment_storage()
    storage.delete(storage_key=storage_key)

    legacy_storage = get_legacy_attachment_storage()
    if legacy_storage is None:
        return
    legacy_storage.delete(storage_key=storage_key)


def get_attachment_storage_readiness() -> tuple[bool, dict]:
    try:
        storage = get_attachment_storage()
    except Exception as exc:
        return (
            False,
            {
                "attachment_storage": "error",
                "attachment_storage_backend": settings.ATTACHMENTS_STORAGE_BACKEND,
                "attachment_storage_error": _describe_storage_error(exc),
            },
        )

    is_ready, checks = storage.readiness_check()
    return (
        is_ready,
        {
            "attachment_storage_backend": settings.ATTACHMENTS_STORAGE_BACKEND,
            **checks,
        },
    )
