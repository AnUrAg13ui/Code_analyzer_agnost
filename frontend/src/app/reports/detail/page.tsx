"use client";

import React, { useEffect, useState, Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import ReactMarkdown from 'react-markdown';
import { ChevronLeft, GitPullRequest, ShieldAlert, Cpu, History, MessageSquare, AlertTriangle, CheckCircle2 } from 'lucide-react';

function ReportContent() {
    const searchParams = useSearchParams();
    const owner = searchParams.get('owner');
    const repo = searchParams.get('repo');
    const pr_number = searchParams.get('pr_number');

    const [report, setReport] = useState<any>(null);
    const [findings, setFindings] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!owner || !repo || !pr_number) return;

        async function fetchData() {
            try {
                const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
                const [reportRes, findingsRes] = await Promise.all([
                    fetch(`${apiUrl}/reports/detail?owner=${owner}&repo=${repo}&pr_number=${pr_number}`),
                    fetch(`${apiUrl}/findings?owner=${owner}&repo=${repo}&pr_number=${pr_number}`)
                ]);
                const reportData = await reportRes.json();
                const findingsData = await findingsRes.json();
                setReport(reportData);
                setFindings(findingsData.findings || []);
            } catch (err) {
                console.error('Failed to fetch detail data', err);
            } finally {
                setLoading(false);
            }
        }
        fetchData();
    }, [owner, repo, pr_number]);

    if (loading) return <div className="p-10 text-center animate-pulse text-primary font-bold text-2xl tracking-widest uppercase">Initializing Deep Scan Results...</div>;
    if (!report) return <div className="p-10 text-center text-red-400 font-bold uppercase tracking-widest">⚠️ Report Not Found in Vault</div>;

    const getAgentIcon = (name: string) => {
        switch (name) {
            case 'bug_detector': return <ShieldAlert className="text-red-400" size={20} />;
            case 'rules_checker': return <ShieldAlert className="text-yellow-400" size={20} />;
            case 'git_history_agent': return <History className="text-blue-400" size={20} />;
            case 'past_pr_agent': return <History className="text-purple-400" size={20} />;
            case 'comment_verifier': return <MessageSquare className="text-green-400" size={20} />;
            default: return <Cpu className="text-primary" size={20} />;
        }
    };

    const formatAgentName = (name: string) => {
        if (!name) return 'Unknown Agent';
        return name.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
    };

    const getSeverityColor = (sev: string) => {
        switch (sev.toLowerCase()) {
            case 'high': return 'bg-red-500/10 text-red-400 border-red-500/20';
            case 'medium': return 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20';
            case 'low': return 'bg-blue-500/10 text-blue-400 border-blue-500/20';
            default: return 'bg-white/5 text-muted-foreground border-white/10';
        }
    };

    return (
        <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700">
            {/* Detail Header */}
            <div className="flex flex-col space-y-4">
                <a href="/reports" className="flex items-center space-x-2 text-primary hover:underline text-sm font-semibold tracking-wider">
                    <ChevronLeft size={16} /> <span>BACK TO VAULT</span>
                </a>
                <div className="flex justify-between items-start">
                    <div className="space-y-2">
                        <h1 className="text-5xl font-black tracking-tight flex items-center gap-4">
                            Review Analysis <span className="text-primary">#{pr_number}</span>
                        </h1>
                        <div className="flex items-center space-x-4 text-muted-foreground text-sm font-medium">
                            <span className="flex items-center gap-1"><GitPullRequest size={16} /> {report.repo}</span>
                            <span className="flex items-center gap-1"><CheckCircle2 size={16} className="text-green-400" /> Confidence: {Math.round(report.avg_confidence * 100)}%</span>
                        </div>
                    </div>
                    <div className="flex flex-col items-end gap-2">
                        <div className="text-xs font-bold text-muted-foreground uppercase tracking-widest">System Outcome</div>
                        <div className="px-4 py-2 bg-primary text-black font-black rounded-lg shadow-xl shadow-primary/20 rotate-1">
                            {report.high_count > 0 ? 'CRITICAL AUDIT' : 'SECURE RELEASE'}
                        </div>
                    </div>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
                {/* Sidebar Summary */}
                <div className="lg:col-span-1 space-y-6">
                    <div className="glass-card rounded-2xl p-6 space-y-6">
                        <h3 className="font-bold border-b border-white/5 pb-2 uppercase tracking-widest text-xs text-muted-foreground">Analysis Summary</h3>
                        <div className="grid grid-cols-1 gap-4">
                            <div className="flex justify-between items-center">
                                <span className="text-sm">Total Findings</span>
                                <span className="font-mono font-bold text-xl">{report.total_findings}</span>
                            </div>
                            <div className="flex justify-between items-center text-red-400">
                                <span className="text-sm">High Risk</span>
                                <span className="font-mono font-bold text-xl">{report.high_count}</span>
                            </div>
                            <div className="flex justify-between items-center text-yellow-500">
                                <span className="text-sm">Medium Risk</span>
                                <span className="font-mono font-bold text-xl">{report.medium_count}</span>
                            </div>
                            <div className="flex justify-between items-center text-blue-400">
                                <span className="text-sm">Low Risk</span>
                                <span className="font-mono font-bold text-xl">{report.low_count}</span>
                            </div>
                        </div>
                    </div>

                    <div className="glass-card rounded-2xl p-6 overflow-auto max-h-[400px]">
                        <h3 className="font-bold border-b border-white/5 pb-2 uppercase tracking-widest text-xs text-muted-foreground mb-4">Raw Markdown Report</h3>
                        <div className="prose prose-invert prose-xs leading-tight opacity-70">
                            <ReactMarkdown>{report.report_markdown}</ReactMarkdown>
                        </div>
                    </div>
                </div>

                {/* Findings List */}
                <div className="lg:col-span-3 space-y-6">
                    <h2 className="text-2xl font-bold tracking-tight border-b border-white/10 pb-4">Agent Findings ({findings.length})</h2>

                    <div className="space-y-4">
                        {findings.length > 0 ? findings.map((f, i) => (
                            <div key={i} className="glass-card rounded-2xl p-6 hover-glow transition-all space-y-4">
                                <div className="flex justify-between items-start">
                                    <div className="flex items-center space-x-3">
                                        <div className="p-2 bg-white/5 rounded-xl border border-white/10">
                                            {getAgentIcon(f.agent_name)}
                                        </div>
                                        <div>
                                            <h4 className="font-bold text-lg leading-tight uppercase tracking-wide">{f.issue_type}</h4>
                                            <p className="text-xs text-muted-foreground font-mono">{f.file_path} {f.line_start ? `:L${f.line_start}` : ''}</p>
                                        </div>
                                    </div>
                                    <div className={`px-3 py-1 rounded-full text-xs font-black uppercase tracking-widest border ${getSeverityColor(f.severity)}`}>
                                        {f.severity}
                                    </div>
                                </div>

                                <div className="p-4 bg-white/5 rounded-xl border border-white/5 text-sm leading-relaxed text-foreground opacity-90 italic">
                                    "{f.description}"
                                </div>

                                <div className="flex justify-between items-center pt-2">
                                    <div className="flex items-center space-x-2 text-xs text-muted-foreground">
                                        <span className="font-semibold uppercase tracking-widest">Confidence:</span>
                                        <span className="bg-primary/10 text-primary px-2 py-0.5 rounded font-mono font-bold">{Math.round((f.confidence || 0) * 100)}%</span>
                                    </div>
                                    <div className="text-[10px] text-muted-foreground italic uppercase">Agent: <span className="font-bold">{formatAgentName(f.agent_name)}</span></div>
                                </div>
                            </div>
                        )) : (
                            <div className="text-center py-20 glass-card rounded-2xl">
                                <AlertTriangle className="mx-auto text-muted-foreground mb-4 opacity-30" size={48} />
                                <p className="text-muted-foreground italic tracking-widest uppercase">No automated findings reported by agents.</p>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

export default function ReportDetailPage() {
    return (
        <Suspense fallback={<div className="p-10 text-center animate-pulse text-primary font-bold text-2xl tracking-widest uppercase">Streaming Insight Stream...</div>}>
            <ReportContent />
        </Suspense>
    );
}
