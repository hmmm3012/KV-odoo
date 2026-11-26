/** @odoo-module **/

import { markup } from "@odoo/owl";
import { escape } from "@web/core/utils/strings";

const ALLOWED = new Set([
    "p",
    "br",
    "strong",
    "em",
    "code",
    "pre",
    "ul",
    "ol",
    "li",
    "a",
    "blockquote",
]);

/**
 * Minimal markdown → safe HTML (bold, italic, inline/code fences, lists).
 * Sanitized without script or event handlers.
 */
export function markdownToSafeMarkup(text) {
    if (!text) {
        return markup("");
    }
    const html = renderMarkdown(escape(text));
    const clean = sanitizeHtml(html);
    return markup(clean);
}

function renderMarkdown(rawEscaped) {
    const lines = rawEscaped.split("\n");
    const out = [];
    let inFence = false;
    let fenceBuf = [];
    let listType = null;

    const flushList = () => {
        if (listType) {
            out.push(listType === "ul" ? "</ul>" : "</ol>");
            listType = null;
        }
    };

    const inline = (line) =>
        line
            .replace(/`([^`]+)`/g, "<code>$1</code>")
            .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
            .replace(/\*([^*]+)\*/g, "<em>$1</em>");

    for (const line of lines) {
        if (line.trim().startsWith("```")) {
            flushList();
            if (inFence) {
                out.push(`<pre><code>${fenceBuf.join("\n")}</code></pre>`);
                fenceBuf = [];
                inFence = false;
            } else {
                inFence = true;
            }
            continue;
        }
        if (inFence) {
            fenceBuf.push(line);
            continue;
        }
        const ul = /^[-*]\s+(.+)$/.exec(line);
        const ol = /^\d+\.\s+(.+)$/.exec(line);
        if (ul) {
            if (listType !== "ul") {
                flushList();
                listType = "ul";
                out.push("<ul>");
            }
            out.push(`<li>${inline(ul[1])}</li>`);
            continue;
        }
        if (ol) {
            if (listType !== "ol") {
                flushList();
                listType = "ol";
                out.push("<ol>");
            }
            out.push(`<li>${inline(ol[1])}</li>`);
            continue;
        }
        flushList();
        if (line.trim() === "") {
            out.push("<br/>");
        } else {
            out.push(`<p>${inline(line)}</p>`);
        }
    }
    flushList();
    if (inFence && fenceBuf.length) {
        out.push(`<pre><code>${fenceBuf.join("\n")}</code></pre>`);
    }
    return out.join("");
}

function sanitizeHtml(html) {
    const doc = new DOMParser().parseFromString(html, "text/html");
    if (typeof window !== "undefined" && window.DOMPurify) {
        return window.DOMPurify.sanitize(doc.body.innerHTML, {
            ALLOWED_TAGS: [...ALLOWED],
            ALLOWED_ATTR: ["href", "target", "rel"],
        });
    }
    walkAndStrip(doc.body);
    return doc.body.innerHTML;
}

function walkAndStrip(node) {
    const remove = [];
    for (const child of [...node.childNodes]) {
        if (child.nodeType === Node.ELEMENT_NODE) {
            const tag = child.tagName.toLowerCase();
            if (!ALLOWED.has(tag)) {
                remove.push(child);
                continue;
            }
            for (const attr of [...child.attributes]) {
                if (attr.name.startsWith("on") || attr.name !== "href") {
                    child.removeAttribute(attr.name);
                }
            }
            if (tag === "a") {
                child.setAttribute("rel", "noopener noreferrer");
                child.setAttribute("target", "_blank");
            }
            walkAndStrip(child);
        }
    }
    for (const el of remove) {
        const text = document.createTextNode(el.textContent || "");
        node.replaceChild(text, el);
    }
}