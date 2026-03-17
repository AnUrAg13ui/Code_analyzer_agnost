"use client";

import React, { useEffect, useState } from 'react';
import { Search, ExternalLink, Calendar, GitPullRequest } from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs));
}

export default function ReportsList() {
    const [reports, setReports] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');

    useEffect(() => {
        async function fetchReports() {
            try {
                const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
                const res = await fetch(`${apiUrl}/reports?limit=100`);

                const data = await res.json();
                setReports(data.reports || []);
            } catch (err) {
                console.error('Failed to fetch reports', err);
            } finally {
                setLoading(false);
            }
        }
        fetchReports();
    }, []);

    const filtered = reports.filter(r =>
        r.repo.toLowerCase().includes(searchTerm.toLowerCase()) ||
        String(r.pr_number).includes(searchTerm)
    );

    return (
        <div className="space-y-8 animate-in fade-in duration-500">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="space-y-1">
                    <h1 className="text-3xl font-extrabold tracking-tight">Analysis Archive</h1>
                    <p className="text-muted-foreground">Browse historical code reviews and security audits.</p>
                </div>

                <div className="relative group">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground group-focus-within:text-primary transition-colors" size={18} />
                    <input
                        type="text"
                        placeholder="Search reports by repo..."
                        className="pl-10 pr-4 py-2 bg-white/5 border border-white/10 rounded-xl outline-none focus:ring-2 focus:ring-primary w-full md:w-64 transition-all"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                    />
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
                {filtered.length > 0 ? filtered.map((r, i) => (
                    <div
                        key={i}
                        className="glass-card hover-glow rounded-2xl p-6 space-y-4 cursor-pointer"
                        onClick={() => window.location.href = `/reports/detail?owner=${r.repo.split('/')[0]}&repo=${r.repo.split('/')[1]}&pr_number=${r.pr_number}`}
                    >
                        <div className="flex justify-between items-start">
                            <div className="p-2 bg-primary/10 text-primary rounded-lg">
                                <GitPullRequest size={20} />
                            </div>
                            <div className="flex space-x-2">
                                <span className="bg-white/5 px-2 py-0.5 rounded text-[10px] font-bold tracking-tighter uppercase text-muted-foreground border border-white/10">v1.2.0</span>
                                <span className="bg-primary/20 text-primary px-2 py-0.5 rounded text-[10px] font-bold tracking-tighter uppercase border border-primary/30">Stable</span>
                            </div>
                        </div>

                        <div className="space-y-1">
                            <div className="font-bold text-lg truncate">{r.repo}</div>
                            <div className="flex items-center text-xs text-muted-foreground space-x-3">
                                <span className="flex items-center gap-1"><Calendar size={12} /> {new Date(r.created_at).toLocaleDateString()}</span>
                                <span className="bg-white/5 px-1.5 py-0.5 rounded">PR #{r.pr_number}</span>
                            </div>
                        </div>

                        <div className="pt-4 border-t border-white/5 flex items-center justify-between">
                            <div className="flex gap-4 font-mono text-xs">
                                <div className="flex flex-col">
                                    <span className="text-muted-foreground uppercase text-[10px]">Findings</span>
                                    <span className="text-foreground font-bold">{r.total_findings}</span>
                                </div>
                                <div className="flex flex-col">
                                    <span className="text-muted-foreground uppercase text-[10px]">Avg Conf</span>
                                    <span className="text-primary font-bold">{Math.round((r.avg_confidence || 0) * 100)}%</span>
                                </div>
                            </div>
                            <ExternalLink size={16} className="text-muted-foreground hover:text-primary transition-colors" />
                        </div>
                    </div>
                )) : (
                    <div className="col-span-full py-20 text-center text-muted-foreground opacity-50 space-y-2">
                        <div className="text-4xl">📭</div>
                        <p>No reports found matching your criteria.</p>
                    </div>
                )}
            </div>
        </div>
    );
}
