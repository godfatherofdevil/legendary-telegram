import type { AttachmentSummary } from "../types";

export type AttachmentPreviewKind = "image" | "video" | "file";
export type AttachmentPreviewMode = "inline" | "explicit-load" | "download-only";

export interface AttachmentPreviewModel {
  kind: AttachmentPreviewKind;
  mode: AttachmentPreviewMode;
  loadLabel: string | null;
  helperText: string | null;
}

export const LARGE_IMAGE_PREVIEW_BYTES = 5 * 1024 * 1024;

export function isImageAttachment(contentType: string): boolean {
  return contentType.toLowerCase().startsWith("image/");
}

export function isVideoAttachment(contentType: string): boolean {
  return contentType.toLowerCase().startsWith("video/");
}

export function formatAttachmentSize(sizeBytes: number): string {
  if (sizeBytes < 1024) {
    return `${sizeBytes} B`;
  }

  const units = ["KB", "MB", "GB"];
  let size = sizeBytes / 1024;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }

  const precision = size >= 10 ? 0 : 1;
  return `${size.toFixed(precision)} ${units[unitIndex]}`;
}

export function getAttachmentPreviewModel(attachment: AttachmentSummary): AttachmentPreviewModel {
  if (isImageAttachment(attachment.content_type)) {
    if (attachment.size_bytes > LARGE_IMAGE_PREVIEW_BYTES) {
      return {
        kind: "image",
        mode: "explicit-load",
        loadLabel: "Load preview",
        helperText: `Large image (${formatAttachmentSize(attachment.size_bytes)})`,
      };
    }

    return {
      kind: "image",
      mode: "inline",
      loadLabel: null,
      helperText: null,
    };
  }

  if (isVideoAttachment(attachment.content_type)) {
    return {
      kind: "video",
      mode: "explicit-load",
      loadLabel: "Load video",
      helperText: `Video preview on demand (${formatAttachmentSize(attachment.size_bytes)})`,
    };
  }

  return {
    kind: "file",
    mode: "download-only",
    loadLabel: null,
    helperText: null,
  };
}
