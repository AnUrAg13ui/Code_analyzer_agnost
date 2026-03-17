"use client";

import React from 'react';
import AnalysisTrigger from '@/components/AnalysisTrigger';
import { Rocket, ShieldCheck, Zap } from 'lucide-react';

export default function ForceScanPage() {
    return (
        <div className="max-w-4xl mx-auto space-y-12 animate-in fade-in slide-in-from-bottom-8 duration-700">
            <div className="text-center space-y-4">
                <h1 className="text-6xl font-black tracking-tighter uppercase">Deep <span className="text-primary italic">Scan</span> Vault</h1>
                <p className="text-muted-foreground text-lg max-w-xl mx-auto">Manual override console. Initiate comprehensive security and logic audits for any GitHub Pull Request on demand.</p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 pb-8 border-b border-white/10">
                <div className="flex flex-col items-center text-center space-y-2">
                    <div className="p-4 bg-primary/10 text-primary rounded-2xl"><Rocket size={28} /></div>
                    <h3 className="font-bold text-sm uppercase tracking-widest">Rapid Ingress</h3>
                    <p className="text-xs text-muted-foreground">High-speed repository ingestion via GitHub API v3.</p>
                </div>
                <div className="flex flex-col items-center text-center space-y-2">
                    <div className="p-4 bg-primary/10 text-primary rounded-2xl"><ShieldCheck size={28} /></div>
                    <h3 className="font-bold text-sm uppercase tracking-widest">Security Filter</h3>
                    <p className="text-xs text-muted-foreground">Ollama-powered deep vulnerability detection.</p>
                </div>
                <div className="flex flex-col items-center text-center space-y-2">
                    <div className="p-4 bg-primary/10 text-primary rounded-2xl"><Zap size={28} /></div>
                    <h3 className="font-bold text-sm uppercase tracking-widest">Real-time Echo</h3>
                    <p className="text-xs text-muted-foreground">Immediate GitHub comment feedback on completion.</p>
                </div>
            </div>

            <div className="shadow-2xl shadow-primary/5">
                <AnalysisTrigger />
            </div>

            <div className="pt-8 text-center text-xs text-muted-foreground uppercase tracking-widest font-mono opacity-50">
        // Connection Secured // 256-bit AES Encryption // Agent Context Ready
            </div>
        </div>
    );
}
