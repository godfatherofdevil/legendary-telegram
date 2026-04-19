# ATTACHMENT_STORAGE_MIGRATION.md

## Purpose

This note documents the M6 attachment-storage migration path from legacy local filesystem blobs to S3-compatible object storage.

## Cutover

1. Keep existing attachment metadata rows unchanged.
2. Configure `ATTACHMENTS_STORAGE_BACKEND=s3` and the `ATTACHMENTS_S3_*` settings against the target MinIO endpoint.
3. Run:

```bash
source .venv/bin/activate
cd backend
python manage.py backfill_attachments_to_object_storage
```

4. Verify the command summary shows no unexpected `missing_source`, `size_mismatch`, or `failed` items.
5. Switch application traffic to the S3-backed configuration only after the backfill report is clean.

During cutover, download requests continue to read legacy filesystem blobs when the object is not yet present in S3. This preserves attachment access while the backfill is in progress, but the intended steady state is still a clean S3 object set.

## Dry Run

Use the same command with `--dry-run` to enumerate pending copies without uploading:

```bash
source .venv/bin/activate
cd backend
python manage.py backfill_attachments_to_object_storage --dry-run
```

## Optional Startup Backfill

Set `ATTACHMENTS_RUN_BACKFILL_ON_STARTUP=1` to run the same backfill command automatically during backend startup when `ATTACHMENTS_STORAGE_BACKEND=s3`.

- The flag is disabled by default.
- The startup backfill remains idempotent.
- This is intended for controlled local or operational rollout steps, not as a replacement for verifying the backfill summary.

## Idempotency

- Existing objects are skipped by `storage_key`.
- Re-running the command does not duplicate objects or mutate attachment metadata.
- `attachments.storage_key` remains the canonical object key before and after migration.

## Missing or Invalid Legacy Blobs

- Missing source files are reported as `missing_source`.
- Source files whose size does not match `attachments.size_bytes` are reported as `size_mismatch`.
- Failed uploads are reported as `failed`.
- These cases are intentionally not auto-repaired; they require operator review before cutover.

## Rollback

- Roll back by restoring `ATTACHMENTS_STORAGE_BACKEND=filesystem`.
- Because metadata is unchanged, rollback does not require database migration.
- Keep legacy filesystem blobs in place until the S3-backed rollout is verified.

## Fallback Expectation

- The filesystem backend remains available for tests, local fallback, and rollback.
- When the S3 backend is active, attachment downloads fall back to legacy filesystem blobs if the S3 object is still missing.
- Public API payloads and authorization rules stay unchanged across both backends.
