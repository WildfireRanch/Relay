/** @type {import('tailwindcss').Config} */
export const content = [
  './app/**/*.{js,ts,jsx,tsx,mdx}',
  './components/**/*.{js,ts,jsx,tsx,mdx}',
  './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  './src/components/**/*.{js,ts,jsx,tsx,mdx}',
  './src/layouts/**/*.{js,ts,jsx,tsx,mdx}',
  './src/**/*.mdx'
];
export const theme = {
  extend: {
    fontFamily: {
      sans: ['var(--font-geist-sans)', 'ui-sans-serif', 'system-ui'],
      mono: ['var(--font-geist-mono)', 'ui-monospace', 'SFMono-Regular']
    },
    borderRadius: {
      sm: 'calc(var(--radius) - 4px)',
      md: 'calc(var(--radius) - 2px)',
      lg: 'var(--radius)',
      xl: 'calc(var(--radius) + 4px)'
    },
    // You can add more: e.g., background, foreground, etc.
    border: 'var(--border)',
    // You can add more: e.g., background, foreground, etc.
  }
};
export const darkMode = 'class';
export const plugins = [require('@tailwindcss/typography')];