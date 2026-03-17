"use client";

import React, { useState } from 'react';

export default function AnalysisTrigger() {
    const [owner, setOwner] = useState('');
    const [repo, setRepo] = useState('');
    const [pr, setPr] = useState('');
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState('');

    const handleScan = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setMessage('');
        try {
            const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
            const res = await fetch(`${apiUrl}/analyze?owner=${owner}&repo=${repo}&pr_number=${pr}`, {
                method: 'POST'
            });
            const data = await res.json();
            setMessage(data.message || 'Analysis started!');
        } catch (err) {
            setMessage('Error starting analysis.');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="glass-card rounded-2xl p-8 space-y-6">
            <div className="flex flex-col space-y-1">
                <h2 className="text-2xl font-bold tracking-tight">Manual Force Scan</h2>
                <p className="text-muted-foreground text-sm">Target any GitHub PR to run a deep AI analysis instantly.</p>
            </div>

            <form onSubmit={handleScan} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                        <label className="text-xs font-semibold uppercase text-muted-foreground ml-1">GitHub Owner</label>
                        <input
                            type="text"
                            placeholder="e.g. facebook"
                            className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 focus:ring-2 focus:ring-primary outline-none transition-all"
                            value={owner}
                            onChange={(e) => setOwner(e.target.value)}
                            required
                        />
                    </div>
                    <div className="space-y-2">
                        <label className="text-xs font-semibold uppercase text-muted-foreground ml-1">Repository</label>
                        <input
                            type="text"
                            placeholder="e.g. react"
                            className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 focus:ring-2 focus:ring-primary outline-none transition-all"
                            value={repo}
                            onChange={(e) => setRepo(e.target.value)}
                            required
                        />
                    </div>
                </div>
                <div className="space-y-2">
                    <label className="text-xs font-semibold uppercase text-muted-foreground ml-1">PR Number</label>
                    <input
                        type="number"
                        placeholder="e.g. 1"
                        className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 focus:ring-2 focus:ring-primary outline-none transition-all"
                        value={pr}
                        onChange={(e) => setPr(e.target.value)}
                        required
                    />
                </div>

                <button
                    disabled={loading}
                    className="w-full bg-primary hover:bg-primary/90 text-black font-bold py-4 rounded-xl shadow-lg transition-transform active:scale-95 disabled:opacity-50"
                >
                    {loading ? 'Initiating Deep Analysis...' : '🚀 Start AI Analysis'}
                </button>
            </form>

            {message && (
                <div className="p-4 bg-primary/10 border border-primary/20 text-primary rounded-xl text-center font-medium animate-in fade-in slide-in-from-bottom-2 duration-300">
                    {message}
                </div>
            )}
        </div>
    );
}
