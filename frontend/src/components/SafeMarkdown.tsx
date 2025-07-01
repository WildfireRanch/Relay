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
  /** Markdown text to render */
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
  // You can expand this for tables, links, images, etc if needed
};

export default function SafeMarkdown({ children, className }: SafeMarkdownProps) {
  // Warn if something other than a string is passed. This helps catch mistakes
  // where a React element or other type might slip through and break rendering.
  if (typeof children !== "string") {
    console.warn(
      "SafeMarkdown expected string, got",
      typeof children,
      children
    );
  }

  const strChildren =
    typeof children === "string" ? children : children ? String(children) : "";

  // Ultra-safe: Escape anything that looks like raw HTML, even before markdown parsing
  // This is a belt-and-suspenders approach since skipHtml and disallowedElements are also set
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
      // If you want to support tables, images, math, etc, add more custom renderers above
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
 */
