// File: preview.ts
// Directory: frontend/.storybook
// Purpose: Global Storybook preview configuration for decorators, controls, and a11y params
// - Adds a global decorator to wrap all stories with React.StrictMode
// - Ensures Framer Motion's AnimatePresence/usePresence works in Storybook

import type { Preview } from '@storybook/nextjs-vite'
import React from 'react';

const preview: Preview = {
  decorators: [
    // Wrap all stories in <React.StrictMode> to provide required context for Framer Motion, etc.
    (Story) => <React.StrictMode><Story /></React.StrictMode>
  ],
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    a11y: {
      // 'todo' - show a11y violations in the test UI only
      // 'error' - fail CI on a11y violations
      // 'off' - skip a11y checks entirely
      test: 'todo'
    }
  },
};

export default preview;
