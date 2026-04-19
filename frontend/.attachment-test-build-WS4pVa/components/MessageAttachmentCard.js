"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.MessageAttachmentCardView = MessageAttachmentCardView;
exports.MessageAttachmentCard = MessageAttachmentCard;
const jsx_runtime_1 = require("react/jsx-runtime");
const react_1 = require("react");
const attachmentPreview_1 = require("../lib/attachmentPreview");
function MessageAttachmentCardView({ attachment, attachmentUrl, previewLoaded, onLoadPreview, }) {
    const preview = (0, attachmentPreview_1.getAttachmentPreviewModel)(attachment);
    const shouldRenderImage = preview.kind === "image" && (preview.mode === "inline" || previewLoaded);
    const shouldRenderVideo = preview.kind === "video" && previewLoaded;
    return ((0, jsx_runtime_1.jsxs)("div", { className: "attachment-card", children: [shouldRenderImage ? ((0, jsx_runtime_1.jsx)("a", { className: "attachment-media-link", href: attachmentUrl, rel: "noreferrer", target: "_blank", children: (0, jsx_runtime_1.jsx)("img", { alt: attachment.filename, className: "attachment-media attachment-image", decoding: "async", loading: "lazy", src: attachmentUrl }) })) : null, shouldRenderVideo ? ((0, jsx_runtime_1.jsxs)("video", { className: "attachment-media attachment-video", controls: true, preload: "metadata", children: [(0, jsx_runtime_1.jsx)("source", { src: attachmentUrl, type: attachment.content_type }), (0, jsx_runtime_1.jsx)("a", { href: attachmentUrl, rel: "noreferrer", target: "_blank", children: attachment.filename })] })) : null, preview.mode === "explicit-load" && !previewLoaded ? ((0, jsx_runtime_1.jsxs)("div", { className: "attachment-preview-shell", children: [(0, jsx_runtime_1.jsx)("p", { children: preview.helperText }), (0, jsx_runtime_1.jsx)("button", { className: "attachment-preview-button", onClick: onLoadPreview, type: "button", children: preview.loadLabel })] })) : null, (0, jsx_runtime_1.jsx)("a", { className: "attachment-link", href: attachmentUrl, rel: "noreferrer", target: "_blank", children: attachment.filename })] }));
}
function MessageAttachmentCard(props) {
    const preview = (0, attachmentPreview_1.getAttachmentPreviewModel)(props.attachment);
    const [previewLoaded, setPreviewLoaded] = (0, react_1.useState)(preview.mode === "inline");
    return ((0, jsx_runtime_1.jsx)(MessageAttachmentCardView, { ...props, onLoadPreview: () => setPreviewLoaded(true), previewLoaded: previewLoaded }));
}
