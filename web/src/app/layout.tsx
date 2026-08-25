import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Build a power plant, or run slower?',
  description:
    'A large AI data center needs as much electricity as a small city, and grid '
    + 'connections now take years. Is it cheaper to build your own power plant, or '
    + 'to let the computers run slightly slower on the worst days? Worked out across '
    + 'two sites, fourteen years of real Texas electricity prices, and every size of '
    + 'grid connection.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
