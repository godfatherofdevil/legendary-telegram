"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.LARGE_IMAGE_PREVIEW_BYTES = void 0;
exports.isImageAttachment = isImageAttachment;
exports.isVideoAttachment = isVideoAttachment;
exports.formatAttachmentSize = formatAttachmentSize;
exports.getAttachmentPreviewModel = getAttachmentPreviewModel;
exports.LARGE_IMAGE_PREVIEW_BYTES = 5 * 1024 * 1024;
function isImageAttachment(contentType) {
    return contentType.toLowerCase().startsWith("image/");
}
function isVideoAttachment(contentType) {
    return contentType.toLowerCase().startsWith("video/");
}
function formatAttachmentSize(sizeBytes) {
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
function getAttachmentPreviewModel(attachment) {
    if (isImageAttachment(attachment.content_type)) {
        if (attachment.size_bytes > exports.LARGE_IMAGE_PREVIEW_BYTES) {
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
