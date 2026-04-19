import { useState } from "react";
import type { AttachmentSummary } from "../types";
import { getAttachmentPreviewModel } from "../lib/attachmentPreview";

interface MessageAttachmentCardProps {
  attachment: AttachmentSummary;
  attachmentUrl: string;
}

interface MessageAttachmentCardViewProps extends MessageAttachmentCardProps {
  previewLoaded: boolean;
  onLoadPreview: () => void;
}

export function MessageAttachmentCardView({
  attachment,
  attachmentUrl,
  previewLoaded,
  onLoadPreview,
}: MessageAttachmentCardViewProps) {
  const preview = getAttachmentPreviewModel(attachment);
  const shouldRenderImage = preview.kind === "image" && (preview.mode === "inline" || previewLoaded);
  const shouldRenderVideo = preview.kind === "video" && previewLoaded;

  return (
    <div className="attachment-card">
      {shouldRenderImage ? (
        <a className="attachment-media-link" href={attachmentUrl} rel="noreferrer" target="_blank">
          <img
            alt={attachment.filename}
            className="attachment-media attachment-image"
            decoding="async"
            loading="lazy"
            src={attachmentUrl}
          />
        </a>
      ) : null}
      {shouldRenderVideo ? (
        <video className="attachment-media attachment-video" controls preload="metadata">
          <source src={attachmentUrl} type={attachment.content_type} />
          <a href={attachmentUrl} rel="noreferrer" target="_blank">
            {attachment.filename}
          </a>
        </video>
      ) : null}
      {preview.mode === "explicit-load" && !previewLoaded ? (
        <div className="attachment-preview-shell">
          <p>{preview.helperText}</p>
          <button className="attachment-preview-button" onClick={onLoadPreview} type="button">
            {preview.loadLabel}
          </button>
        </div>
      ) : null}
      <a className="attachment-link" href={attachmentUrl} rel="noreferrer" target="_blank">
        {attachment.filename}
      </a>
    </div>
  );
}

export function MessageAttachmentCard(props: MessageAttachmentCardProps) {
  const preview = getAttachmentPreviewModel(props.attachment);
  const [previewLoaded, setPreviewLoaded] = useState(preview.mode === "inline");

  return (
    <MessageAttachmentCardView
      {...props}
      onLoadPreview={() => setPreviewLoaded(true)}
      previewLoaded={previewLoaded}
    />
  );
}
