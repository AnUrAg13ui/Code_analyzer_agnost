import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI Code Analyzer | Deep Intelligence",
  description: "Advanced AI-powered code analysis and security auditing dashboard.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background text-foreground flex min-h-screen`}
      >
        {/* Sidebar */}
        <aside className="w-64 border-r border-border bg-card flex flex-col p-6 space-y-8">
          <div className="flex items-center space-x-2">
            <div className="w-8 h-8 rounded bg-primary flex items-center justify-center font-bold text-black animate-pulse">
              A
            </div>
            <span className="text-xl font-bold tracking-tight">Code Analyzer</span>
          </div>

          <nav className="flex-1 space-y-2">
            <a href="/" className="flex items-center space-x-3 px-4 py-2 rounded-lg bg-primary/10 text-primary hover-glow">
              <span className="text-lg">📊</span>
              <span className="font-medium">Dashboard</span>
            </a>
            <a href="/reports" className="flex items-center space-x-3 px-4 py-2 rounded-lg hover:bg-white/5 transition-colors">
              <span className="text-lg">📁</span>
              <span className="font-medium">All Reports</span>
            </a>
            <a href="/analyze" className="flex items-center space-x-3 px-4 py-2 rounded-lg hover:bg-white/5 transition-colors">
              <span className="text-lg">🚀</span>
              <span className="font-medium">Force Scan</span>
            </a>
            <a href="/testing_frontend" className="flex items-center space-x-3 px-4 py-2 rounded-lg hover:bg-white/5 transition-colors">
              <span className="text-lg">🧪</span>
              <span className="font-medium">Testing UI</span>
            </a>
            <a href="/rules" className="flex items-center space-x-3 px-4 py-2 rounded-lg hover:bg-white/5 transition-colors">
              <span className="text-lg">🛡️</span>
              <span className="font-medium">Coding Rules</span>
            </a>
          </nav>

          <div className="pt-4 border-t border-border mt-auto">
            <div className="text-xs text-muted-foreground uppercase tracking-wider font-semibold mb-2">System Status</div>
            <div className="flex items-center space-x-2 text-sm text-green-400">
              <div className="w-2 h-2 rounded-full bg-green-400"></div>
              <span>LLM Reachable</span>
            </div>
          </div>
        </aside>

        {/* Main Content */}
        <main className="flex-1 overflow-auto relative bg-[#050505]">
          {/* Subtle Glow Background */}
          <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-primary/5 rounded-full blur-[120px] pointer-events-none"></div>
          <div className="p-8 relative">
            {children}
          </div>
        </main>
      </body>
    </html>
  );
}
