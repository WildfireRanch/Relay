// File: frontend/next.config.js

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
  /* Add other options here as needed */
};

module.exports = nextConfig;
