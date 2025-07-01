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
    // Extract language from className (e.g., "language-js")
    const match = /language-(\w+)/.exec(className || "");
    if (!inline && match) {
      // Block code: highlight with Prism
      return (
        <SyntaxHighlighter
          style={vscDarkPlus}
          language={match[1]}
          PreTag="div"
          {...rest}
        >
          {String(children).replace(/\n$/, "")}
        </SyntaxHighlighter>
      );
    }
    // Inline code: render as <code>
    return (
      <code {...(className ? { className } : {})} {...rest}>
        {String(children)}
      </code>
    );
  },
  // Example expansion for custom tables, links, images:
  // table({ children, ...props }) { ... },
  // a({ href, children, ...props }) { ... },
  // img({ src, alt, ...props }) { ... },
};

export default function SafeMarkdown({ children, className }: SafeMarkdownProps) {
  // Dev-only: warn if a non-string slips through (should never happen in production)
  if (typeof children !== "string") {
    if (process.env.NODE_ENV !== "production") {
      console.warn(
        "[SafeMarkdown] Expected children to be a string, got:",
        typeof children,
        children
      );
    }
  }

  // Always coerce to string
  const strChildren =
    typeof children === "string" ? children : children ? String(children) : "";

  // Escape anything that looks like raw HTML before parsing as markdown
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
      // Add more custom renderers above as needed (tables, math, images)
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
