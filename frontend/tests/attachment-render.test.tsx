import React from "react";
import ReactDOMServer from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MessageAttachmentCardView } from "../src/components/MessageAttachmentCard";
import { getAttachmentPreviewModel } from "../src/lib/attachmentPreview";
import type { AttachmentSummary } from "../src/types";

function buildAttachment(overrides: Partial<AttachmentSummary> = {}): AttachmentSummary {
  return {
    id: "att_01",
    filename: "preview.bin",
    content_type: "application/octet-stream",
    size_bytes: 512,
    comment: null,
    download_url: "/api/v1/attachments/att_01/download",
    ...overrides,
  };
}

function renderAttachmentCard(attachment: AttachmentSummary, previewLoaded = false): string {
  return ReactDOMServer.renderToStaticMarkup(
    <MessageAttachmentCardView
      attachment={attachment}
      attachmentUrl={attachment.download_url}
      onLoadPreview={() => {}}
      previewLoaded={previewLoaded}
    />,
  );
}

describe("MessageAttachmentCardView", () => {
  it("renders small image attachments inline", () => {
    const attachment = buildAttachment({
      filename: "small.png",
      content_type: "image/png",
      size_bytes: 512_000,
    });

    const preview = getAttachmentPreviewModel(attachment);
    const html = renderAttachmentCard(attachment);

    expect(preview.mode).toBe("inline");
    expect(html).toMatch(/<img/);
    expect(html).not.toMatch(/Load preview/);
  });

  it("requires explicit loading for large image previews", () => {
    const attachment = buildAttachment({
      filename: "large.png",
      content_type: "image/png",
      size_bytes: 7 * 1024 * 1024,
    });

    const preview = getAttachmentPreviewModel(attachment);
    const html = renderAttachmentCard(attachment);

    expect(preview.mode).toBe("explicit-load");
    expect(html).toMatch(/Load preview/);
    expect(html).not.toMatch(/<img/);
  });

  it("avoids eager video rendering until the preview is requested", () => {
    const attachment = buildAttachment({
      filename: "clip.mp4",
      content_type: "video/mp4",
      size_bytes: 24 * 1024 * 1024,
    });

    const preview = getAttachmentPreviewModel(attachment);
    const unloadedHtml = renderAttachmentCard(attachment, false);
    const loadedHtml = renderAttachmentCard(attachment, true);

    expect(preview.mode).toBe("explicit-load");
    expect(unloadedHtml).toMatch(/Load video/);
    expect(unloadedHtml).not.toMatch(/<video/);
    expect(loadedHtml).toMatch(/<video/);
    expect(loadedHtml).toMatch(/preload="metadata"/);
  });
});
