// File: src/components/SafeMarkdown.tsx
// Purpose: Bulletproof, consistent, and safe Markdown rendering for all app content.
//          Hardened against XSS, raw HTML, and rendering bugs. All code blocks are syntax-highlighted (Prism).
//          This is the ONLY allowed way to render Markdown in the app.

import React from "react";
import ReactMarkdown, { Components } from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

// Props for the SafeMarkdown component
type SafeMarkdownProps = {
  /** Markdown text to render (always a string) */
  children: string;
  /** Optional CSS className for wrapper */
  className?: string;
};

// Custom Markdown renderer for code blocks (uses Prism for highlighting)
const markdownComponents: Components = {
  code(props) {
    const { inline, className, children, ...rest } = props as {
      inline?: boolean;
      className?: string;
      children: React.ReactNode;
    };
    const match = /language-(\w+)/.exec(className || "");
    const content = String(children).replace(/\n$/, "");

    if (!inline && match) {
      return (
        <SyntaxHighlighter
          style={vscDarkPlus}
          language={match[1]}
          PreTag="div"
          {...rest}
        >
          {content}
        </SyntaxHighlighter>
      );
    }

    return (
      <code {...(className ? { className } : {})} {...rest}>
        {content}
      </code>
    );
  },
  // You can expand here for tables, images, links if needed
};

export default function SafeMarkdown({ children, className }: SafeMarkdownProps) {
  // Dev-only: Warn if a non-string slips through (should never happen in production)
  if (typeof children !== "string" && process.env.NODE_ENV !== "production") {
    console.warn(
      "[SafeMarkdown] Expected children to be a string, got:",
      typeof children,
      children
    );
  }

  // Always coerce to string for React safety
  const strChildren =
    typeof children === "string" ? children : children ? String(children) : "";

  // Debug: Log if somehow a non-string is still about to render (for final #418 hunting)
  if (typeof strChildren !== "string") {
    // eslint-disable-next-line no-console
    console.error("SAFE-MARKDOWN-418-DEBUG", typeof strChildren, strChildren);
  }

  // Ultra-safe: Escape anything that looks like raw HTML before markdown parsing
  // (belt-and-suspenders, since skipHtml & disallowedElements are also set)
  const likelyRawHtml = /<\s*[a-zA-Z]+[^>]*>/.test(strChildren);
  const safeChildren = likelyRawHtml
    ? strChildren.replace(/</g, "&lt;").replace(/>/g, "&gt;")
    : strChildren;

  return (
    <ReactMarkdown
      components={markdownComponents}
      // SECURITY: Never allow any HTML passthrough from markdown
      skipHtml={true}
      disallowedElements={["html", "head", "body", "style", "script", "iframe"]}
      {...(className ? { className } : {})}
    >
      {safeChildren}
    </ReactMarkdown>
  );
}

/**
 * Usage:
 * <SafeMarkdown>{markdownString}</SafeMarkdown>
 *
 * - NEVER use ReactMarkdown directly in any other file.
 * - All markdown content (LLM, docs, search, context, etc) MUST be rendered via SafeMarkdown.
 * - Always ensure children is a string (coerce using toMDString or similar as needed).
 */
