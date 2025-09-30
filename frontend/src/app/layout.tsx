import './globals.css';
import { ReactNode } from 'react';
import Sidebar from '@/components/Sidebar/Sidebar';

// Force dynamic rendering to avoid SSR issues with client components
export const dynamic = 'force-dynamic';

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans bg-background text-foreground">
        <div className="flex h-screen">
          <Sidebar />
          <main className="flex-1 overflow-auto p-6 bg-gray-50">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
