// File: frontend/next.config.js

const path = require('path');

/**
 * @type {import('next').NextConfig}
 */
const nextConfig = {
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  // Skip generating 404 during build to avoid SSR issues with client components
  skipTrailingSlashRedirect: true,
  // Disable prerendering for error pages
  experimental: {
    optimizePackageImports: ['lucide-react'],
  },
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      '@': path.resolve(__dirname, 'src'),
      '@/components': path.resolve(__dirname, 'src/components'),
      '@/lib': path.resolve(__dirname, 'src/lib'),
    };
    return config;
  },
  /* Add other options here as needed */
};

module.exports = nextConfig;
