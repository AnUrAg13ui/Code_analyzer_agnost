"use client";

import React, { useEffect, useState } from 'react';
import StatCard from '@/components/StatCard';
import AnalysisTrigger from '@/components/AnalysisTrigger';

interface ReportSummary {
  repo: string;
  pr_number: number;
  total_findings: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  avg_confidence: number;
  created_at: string;
}

export default function Dashboard() {
  const [stats, setStats] = useState<any>(null);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
        const [statsRes, reportsRes] = await Promise.all([
          fetch(`${apiUrl}/stats`),
          fetch(`${apiUrl}/reports?limit=5`)
        ]);
        const statsData = await statsRes.json();
        const reportsData = await reportsRes.json();
        setStats(statsData);
        setReports(reportsData.reports || []);
      } catch (err) {
        console.error('Failed to fetch dashboard data', err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  return (
    <div className="space-y-10">
      {/* Header Section */}
      <div className="flex justify-between items-end">
        <div className="space-y-2">
          <h1 className="text-4xl font-extrabold tracking-tight">AI Analysis Dashboard</h1>
          <p className="text-muted-foreground">Deep intelligence for security, logic, and code quality.</p>
        </div>
        <div className="text-right">
          <div className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-1">Current Intelligence</div>
          <div className="text-sm font-mono text-primary bg-primary/10 px-3 py-1 rounded-full border border-primary/20">DeepSeek-Coder V2 (Ollama)</div>
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <StatCard
          title="Total PRs Analyzed"
          value={stats?.summary?.total_prs || 0}
          icon="📦"
          trend="+12% from last week"
        />
        <StatCard
          title="Deep Findings"
          value={stats?.summary?.total_findings || 0}
          icon="🛡️"
          trend="8% security related"
        />
        <StatCard
          title="High Risk Modules"
          value={stats?.summary?.high_risk_modules || 0}
          icon="⚠️"
          trend="Requires urgent review"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-10">
        {/* Recent Reports Table */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex justify-between items-center">
            <h2 className="text-2xl font-bold tracking-tight">Recent Analysis Logs</h2>
            <a href="/reports" className="text-sm font-medium text-primary hover:underline">View All &rarr;</a>
          </div>

          <div className="glass-card rounded-2xl overflow-hidden">
            <table className="w-full text-left">
              <thead>
                <tr className="bg-white/5 text-muted-foreground text-xs uppercase font-bold">
                  <th className="px-6 py-4">Repository / PR</th>
                  <th className="px-6 py-4">Status</th>
                  <th className="px-6 py-4">Findings (H/M/L)</th>
                  <th className="px-6 py-4">Confidence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {reports.length > 0 ? reports.map((r, i) => (
                  <tr key={i} className="hover:bg-white/5 transition-colors cursor-pointer" onClick={() => window.location.href = `/reports/detail?owner=${r.repo.split('/')[0]}&repo=${r.repo.split('/')[1]}&pr_number=${r.pr_number}`}>
                    <td className="px-6 py-5">
                      <div className="font-semibold text-foreground">{r.repo}</div>
                      <div className="text-xs text-muted-foreground">PR #{r.pr_number} • {new Date(r.created_at).toLocaleDateString()}</div>
                    </td>
                    <td className="px-6 py-5">
                      <span className="bg-green-500/10 text-green-400 text-xs px-2 py-1 rounded-full font-medium border border-green-500/20">Analyzed</span>
                    </td>
                    <td className="px-6 py-5">
                      <div className="flex space-x-2 font-mono text-sm leading-none">
                        <span className="text-red-400">{r.high_count}</span>
                        <span className="text-muted-foreground">/</span>
                        <span className="text-yellow-400">{r.medium_count}</span>
                        <span className="text-muted-foreground">/</span>
                        <span className="text-blue-400">{r.low_count}</span>
                      </div>
                    </td>
                    <td className="px-6 py-5">
                      <div className="flex items-center space-x-2">
                        <div className="w-12 h-1.5 bg-white/10 rounded-full overflow-hidden">
                          <div className="h-full bg-primary" style={{ width: `${(r.avg_confidence || 0) * 100}%` }}></div>
                        </div>
                        <span className="text-xs font-mono">{Math.round((r.avg_confidence || 0) * 100)}%</span>
                      </div>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={4} className="px-6 py-10 text-center text-muted-foreground italic">No analysis history found.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Trigger Sidebar */}
        <div className="space-y-8">
          <AnalysisTrigger />

          <div className="glass-card rounded-2xl p-6 space-y-4">
            <h3 className="font-bold">Top At-Risk Files</h3>
            <div className="space-y-3">
              {stats?.top_risks?.map((m: any, i: number) => (
                <div key={i} className="flex justify-between items-center text-sm p-2 hover:bg-white/5 rounded-lg">
                  <span className="truncate max-w-[150px] font-mono opacity-80">{m.module_name}</span>
                  <span className="bg-red-500/10 text-red-400 px-2 py-0.5 rounded text-xs font-bold border border-red-500/20">{m.risk_score.toFixed(1)}</span>
                </div>
              ))}
              {!stats?.top_risks?.length && <div className="text-muted-foreground italic text-xs">No risk data available.</div>}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
