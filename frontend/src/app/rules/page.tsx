"use client";

import React, { useEffect, useState } from 'react';
import { Search, ShieldAlert, Cpu, Hash, FileText } from 'lucide-react';

interface Rule {
    id: number;
    rule_name: string;
    rule_description: string;
    category: string;
    severity: string;
    enabled: boolean;
}

export default function RulesPage() {
    const [rules, setRules] = useState<Rule[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');

export default function RulesPage() {
    const [rules, setRules] = useState<Rule[]>([]);
    const [loading, setLoading] = useState(true);
    const [searchTerm, setSearchTerm] = useState('');
    const [message, setMessage] = useState('');

    useEffect(() => {
        async function fetchRules() {
            try {
                const realRes = await fetch('http://127.0.0.1:8000/rules');
                const data = await realRes.json();
                setRules(data.rules || []);
                setMessage(data.message || '');
            } catch (err) {
                console.error('Failed to fetch rules', err);
                setMessage('Unable to connect to the backend. Please ensure the server is running.');
            } finally {
                setLoading(false);
            }
        }
        fetchRules();
    }, []);

    const filtered = rules.filter(r =>
        r.rule_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        r.rule_description.toLowerCase().includes(searchTerm.toLowerCase())
    );

    const getCategoryIcon = (cat: string) => {
        switch (cat.toLowerCase()) {
            case 'security': return <ShieldAlert size={18} />;
            case 'arch': return <Cpu size={18} />;
            case 'style': return <FileText size={18} />;
            default: return <Hash size={18} />;
        }
    };

    return (
        <div className="space-y-10 animate-in fade-in duration-500">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="space-y-2">
                    <h1 className="text-4xl font-extrabold tracking-tight">AI-Powered Analysis</h1>
                    <p className="text-muted-foreground">The system now uses advanced AI reasoning instead of predefined coding rules for more intelligent and context-aware code analysis.</p>
                </div>

                <div className="relative group">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground group-focus-within:text-primary transition-colors" size={18} />
                    <input
                        type="text"
                        placeholder="Search analysis patterns..."
                        className="pl-10 pr-4 py-2 bg-white/5 border border-white/10 rounded-xl outline-none focus:ring-2 focus:ring-primary w-full md:w-64 transition-all"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                    />
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {filtered.length > 0 ? filtered.map((r, i) => (
                    <div key={i} className="glass-card rounded-2xl p-6 border-l-4 border-l-primary hover-glow space-y-4">
                        <div className="flex justify-between items-start">
                            <div className="flex flex-col space-y-1">
                                <h2 className="text-xl font-bold tracking-tight uppercase">{r.rule_name}</h2>
                                <div className="flex items-center space-x-2 text-primary font-mono text-[10px] uppercase tracking-widest">
                                    {getCategoryIcon(r.category)} <span>{r.category}</span>
                                </div>
                            </div>
                            <div className={`px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-widest border border-white/10 ${r.severity === 'high' ? 'text-red-400 bg-red-400/10' : 'text-blue-400 bg-blue-400/10'}`}>
                                {r.severity}
                            </div>
                        </div>

                        <p className="text-sm text-muted-foreground leading-relaxed italic opacity-90">
                            "{r.rule_description}"
                        </p>

                        <div className="flex justify-between items-center pt-2">
                            <span className="text-[10px] font-bold text-muted-foreground uppercase opacity-50 tracking-tighter">Status & Integrity</span>
                            <div className="flex items-center space-x-2">
                                <span className="w-2 h-2 rounded-full bg-green-400"></span>
                                <span className="text-[10px] font-bold text-green-400 uppercase tracking-widest">Active</span>
                            </div>
                        </div>
                    </div>
                )) : (
                    <div className="col-span-full py-20 text-center text-muted-foreground opacity-50">
                        {loading ? "Decrypting logic patterns..." : message || "No active rules found matching your search."}
                    </div>
                )}
            </div>
        </div>
    );
}
