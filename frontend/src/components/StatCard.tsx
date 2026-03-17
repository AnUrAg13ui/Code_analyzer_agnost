import React from 'react';

interface StatCardProps {
    title: string;
    value: string | number;
    icon: string;
    trend?: string;
}

export default function StatCard({ title, value, icon, trend }: StatCardProps) {
    return (
        <div className="glass-card rounded-2xl p-6 flex flex-col space-y-2 hover-glow flex-1 min-w-[200px]">
            <div className="flex justify-between items-center text-muted-foreground">
                <span className="text-sm font-semibold tracking-wider uppercase">{title}</span>
                <span className="text-xl">{icon}</span>
            </div>
            <div className="text-3xl font-bold tracking-tight">{value}</div>
            {trend && (
                <div className="text-xs text-green-400 font-medium">
                    {trend}
                </div>
            )}
        </div>
    );
}
