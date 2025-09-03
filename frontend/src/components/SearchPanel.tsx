// File: src/components/SafeMarkdown.tsx
// Purpose: Bulletproof, consistent, and safe Markdown rendering for all app content.
// - XSS-hardened: no raw HTML passthrough; safe link handling (noopener/noreferrer)
// - GFM support: tables, autolinks, strikethrough, task lists
// - Async Prism code highlighting (smaller bundle), graceful fallback inline <code>
// - This is the ONLY allowed way to render Markdown in the app.

"use client";

import React, { memo, useMemo } from "react";
import ReactMarkdown, { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { PrismAsyncLight as SyntaxHighlighter } from "react-syntax-highlighter";
// Tip: use a lightweight theme; can swap to vscDarkPlus if you prefer.
// Async import keeps it from bloating the initial bundle.
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

// If you want to pre-register a few common languages, you can lazy-register here
// to keep the bundle lean. Example (uncomment as needed):
// import js from "react-syntax-highlighter/dist/esm/languages/prism/javascript";
// import ts from "react-syntax-highlighter/dist/esm/languages/prism/typescript";
// import json from "react-syntax-highlighter/dist/esm/languages/prism/json";
// SyntaxHighlighter.registerLanguage("javascript", js);
// SyntaxHighlighter.registerLanguage("typescript", ts);
// SyntaxHighlighter.registerLanguage("json", json);

type SafeMarkdownProps = {
  /** Markdown text to render (always a string) */
  children: string;
  /** Optional CSS className for wrapper */
  className?: string;
};

// Helpers
function isExternal(href: string) {
  try {
    const u = new URL(href, "http://local"); // base to parse relative urls safely
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

const markdownComponents: Components = {
  // Safe links: open external in new tab with rel protections
  a({ href = "", children, ...rest }) {
    const external = isExternal(href);
    const common = {
      href,
      ...rest,
      ...(external
        ? { target: "_blank", rel: "noopener noreferrer" }
        : undefined),
    };
    return <a {...common}>{children}</a>;
  },

  // Safe images: no remote JS, lazy load
  img({ src = "", alt, title, ...rest }) {
    // You could whitelist domains here if you want even tighter control.
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt={typeof alt === "string" ? alt : ""}
        title={typeof title === "string" ? title : undefined}
        loading="lazy"
        decoding="async"
        referrerPolicy="no-referrer"
        {...rest}
      />
    );
  },

  // Code blocks with Prism async highlighter
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
        <SyntaxHighlighter
          style={vscDarkPlus}
          language={language}
          PreTag="div"
          {...rest}
        >
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

  // You can extend tables, blockquotes, etc. here if you want custom styling
};

function Inner({ children, className }: SafeMarkdownProps) {
  // Dev-only: warn if a non-string slips through
  if (typeof children !== "string" && process.env.NODE_ENV !== "production") {
    // eslint-disable-next-line no-console
    console.warn("[SafeMarkdown] Expected string children, got:", typeof children, children);
  }

  // Always coerce to string for React safety
  const str = typeof children === "string" ? children : children ? String(children) : "";

  // Belt-and-suspenders: we already forbid HTML via skipHtml, but if someone
  // pastes raw tags, escape angle brackets to keep previews readable.
  const looksLikeHtml = /<\s*[a-zA-Z]+[^>]*>/.test(str);
  const safe = looksLikeHtml ? str.replace(/</g, "&lt;").replace(/>/g, "&gt;") : str;

  // Memoize the markdown to avoid re-render cost for long docs
  const md = useMemo(() => safe, [safe]);

  return (
    <ReactMarkdown
      // SECURITY: never allow raw HTML passthrough from markdown
      skipHtml={true}
      disallowedElements={["html", "head", "body", "style", "script", "iframe", "object", "embed", "link"]}
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
