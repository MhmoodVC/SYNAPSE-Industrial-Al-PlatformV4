import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'SYNAPSE | Autonomous Industrial Health & Decision Engine',
  description: 'Industrial health monitoring, decision arena, and prognostics for centrifugal pumps',
  icons: {
    icon: '/synapse_logo.png',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-[#F8FAFC] text-[#0F172A] min-h-screen">
        {children}
      </body>
    </html>
  );
}
