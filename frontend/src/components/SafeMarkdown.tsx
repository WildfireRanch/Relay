// File: src/components/SafeMarkdown.tsx
// Purpose: Bulletproof, consistent, and safe Markdown rendering for all app content.
// Security model:
//  - No raw HTML pass-through (skipHtml + explicit disallowedElements)
//  - Strict URL sanitization for <a> and <img> (no javascript:, no file:, data: links)
//  - External links open in new tab with rel protections (noopener, noreferrer, nofollow)
// Features:
//  - GitHub-flavored Markdown (GFM): tables, autolinks, strikethrough, task lists
//  - Async Prism code highlighting for fenced blocks; lightweight inline <code> fallback
//  - Lazy loaded images with referrer policy
//
// Usage: This is the ONLY allowed way to render Markdown in the app.

"use client";

import React, { memo, useMemo } from "react";
import ReactMarkdown, { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { PrismAsyncLight as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

type SafeMarkdownProps = {
  /** Markdown text to render (always a string) */
  children: string;
  /** Optional CSS className for wrapper */
  className?: string;
};

/* ────────────────────────────────────────────────────────────────────────────
 * URL / SRC SANITIZATION
 * ---------------------------------------------------------------------------
 * We allow:
 *   Links: http, https, mailto, tel, and relative URLs.
 *   Images: http, https, and data:image/(png|jpeg|gif|webp) ONLY (no SVG to avoid XSS).
 * Everything else is dropped (renders as plain text for links; image omitted).
 */

function isRelative(url: string): boolean {
  // "/path", "./x", "../y"
  return /^\.{0,2}\//.test(url) || url.startsWith("/");
}

function getScheme(url: string): string | null {
  const m = /^[a-zA-Z][a-zA-Z0-9+.-]*:/.exec(url);
  return m ? m[0].slice(0, -1).toLowerCase() : null;
}

function sanitizeHref(href: string | undefined): string | null {
  if (!href) return null;
  try {
    // Allow relative URLs outright
    if (isRelative(href)) return href;

    const scheme = getScheme(href);
    if (!scheme) {
      // Something like "example.com" without scheme → treat as relative (safe)
      return href;
    }
    if (scheme === "http" || scheme === "https" || scheme === "mailto" || scheme === "tel") {
      return href;
    }
    // Block javascript:, data:, file:, vbscript:, etc.
    return null;
  } catch {
    return null;
  }
}

function sanitizeImgSrc(src: string | undefined): string | null {
  if (!src) return null;
  try {
    if (isRelative(src)) return src;

    const scheme = getScheme(src);
    if (!scheme) return null;

    if (scheme === "http" || scheme === "https") return src;

    // Allow safe data URIs for raster images only (no SVG)
    if (scheme === "data") {
      // e.g., data:image/png;base64,....
      if (/^data:image\/(png|jpe?g|gif|webp);/i.test(src)) return src;
      return null;
    }
    return null;
  } catch {
    return null;
  }
}

/* ────────────────────────────────────────────────────────────────────────────
 * MARKDOWN RENDERERS
 * ---------------------------------------------------------------------------
 * - Links: sanitized href; external links open new tab + rel protections.
 * - Images: sanitized src; lazy-loaded; no svg/data-svg.
 * - Code: fenced blocks highlighted via Prism; inline code is lightweight.
 */

const markdownComponents: Components = {
  a({ href, children, ...rest }) {
    const safeHref = sanitizeHref(typeof href === "string" ? href : undefined);
    if (!safeHref) {
      // Render as plain text if unsafe or invalid
      return <span {...rest}>{children}</span>;
    }
    const isExternal = safeHref.startsWith("http://") || safeHref.startsWith("https://");
    const common = {
      href: safeHref,
      ...rest,
      ...(isExternal ? { target: "_blank", rel: "noopener noreferrer nofollow" } : undefined),
    };
    return <a {...common}>{children}</a>;
  },

  img({ src, alt, title, ...rest }) {
    // `src` can be string | Blob | undefined in newer DOM type defs; coerce to string
    const srcStr = typeof src === "string" ? src : undefined;
    const safeSrc = sanitizeImgSrc(srcStr);
    if (!safeSrc) {
      // Drop unsafe images entirely
      return null;
    }
    // eslint-disable-next-line @next/next/no-img-element
    return (
      <img
        src={safeSrc}
        alt={typeof alt === "string" ? alt : ""}
        title={typeof title === "string" ? title : undefined}
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        {...rest}
      />
    );
  },

  code(props) {
    const { inline, className, children, ...rest } = props as {
      inline?: boolean;
      className?: string;
      children: React.ReactNode;
    };

    const match = /language-(\w+)/.exec(className || "");
    const content = String(children ?? "").replace(/\n$/, "");

    if (!inline && match) {
      const language = match[1];
      return (
        <SyntaxHighlighter style={vscDarkPlus} language={language} PreTag="div" {...rest}>
          {content}
        </SyntaxHighlighter>
      );
    }

    // Inline code fallback (no heavy highlighter)
    return (
      <code {...(className ? { className } : {})} {...rest}>
        {content}
      </code>
    );
  },
};

/* ────────────────────────────────────────────────────────────────────────────
 * COMPONENT
 * ---------------------------------------------------------------------------
 * - Coerces non-string children
 * - Escapes raw angle brackets as belt-and-suspenders (skipHtml already blocks)
 * - Memoizes the final string to cut re-render cost on long content
 */

function Inner({ children, className }: SafeMarkdownProps) {
  if (typeof children !== "string" && process.env.NODE_ENV !== "production") {
    // eslint-disable-next-line no-console
    console.warn("[SafeMarkdown] Expected string children, got:", typeof children, children);
  }

  // Always coerce to string for React safety
  const str = typeof children === "string" ? children : children ? String(children) : "";

  // Human-friendly safety: keep literal tags from being eaten by Markdown
  const looksLikeHtml = /<\s*[a-zA-Z]+[^>]*>/.test(str);
  const safe = looksLikeHtml ? str.replace(/</g, "&lt;").replace(/>/g, "&gt;") : str;

  const md = useMemo(() => safe, [safe]);

  return (
    <ReactMarkdown
      // SECURITY: never allow raw HTML passthrough from markdown
      skipHtml={true}
      disallowedElements={["html", "head", "body", "style", "script", "iframe", "object", "embed", "link", "meta"]}
      // GitHub-flavored Markdown (tables, autolinks, strikethrough, task lists)
      remarkPlugins={[remarkGfm]}
      components={markdownComponents}
      {...(className ? { className } : {})}
    >
      {md}
    </ReactMarkdown>
  );
}

const SafeMarkdown = memo(Inner);
export default SafeMarkdown;
