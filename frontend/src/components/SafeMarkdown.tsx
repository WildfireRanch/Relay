// File: src/components/SafeMarkdown.tsx

import React from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

type SafeMarkdownProps = {
  children: string;
  className?: string;
};

const markdownComponents: Components = {
  code(props) {
    const { inline, className, children, ...rest } = props as {
      inline?: boolean;
      className?: string;
      children: React.ReactNode;
    };
    const match = /language-(\w+)/.exec(className || "");
    return !inline && match ? (
      <SyntaxHighlighter
        style={vscDarkPlus}
        language={match[1]}
        PreTag="div"
        {...rest}
      >
        {String(children).replace(/\n$/, "")}
      </SyntaxHighlighter>
    ) : (
      <code {...(className ? { className } : {})} {...rest}>
        {String(children)}
      </code>
    );
  }
};

export default function SafeMarkdown({ children, className }: SafeMarkdownProps) {
  // Final, ultimate fix: escape anything that looks like raw HTML
  const likelyRawHtml = /<\s*[a-zA-Z]+[^>]*>/.test(children);
  const safeChildren = likelyRawHtml
    ? children.replace(/</g, "&lt;").replace(/>/g, "&gt;")
    : children;

  return (
    <ReactMarkdown
      components={markdownComponents}
      skipHtml={true}
      disallowedElements={["html", "head", "body", "style", "script", "iframe"]}
      {...(className ? { className } : {})}
    >
      {safeChildren}
    </ReactMarkdown>
  );
}
