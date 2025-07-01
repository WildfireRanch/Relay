import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import SafeMarkdown from '../src/components/SafeMarkdown';

describe('SafeMarkdown', () => {
  it('renders markdown strings without warning', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const html = renderToStaticMarkup(<SafeMarkdown>**bold**</SafeMarkdown>);
    expect(html).toContain('<strong>bold</strong>');
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });

  it('warns when non-string is provided', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const html = renderToStaticMarkup(
      <SafeMarkdown>{123 as unknown as string}</SafeMarkdown>
    );
    expect(html).toContain('123');
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });
});
