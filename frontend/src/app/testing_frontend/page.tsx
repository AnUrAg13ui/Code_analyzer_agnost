"use client";

import React, { useEffect, useState } from "react";

type Finding = {
  id: number;
  file_path: string;
  issue_type: string;
  severity: string;
  description: string;
  agent_name: string;
  raw_response: string;
};

type ReportDetail = {
  repo: string;
  pr_number: number;
  total_findings: number;
  avg_confidence: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  report_markdown: string;
};

export default function TestingFrontend() {
  const [owner, setOwner] = useState("");
  const [repo, setRepo] = useState("");
  const [prNumber, setPrNumber] = useState("");

  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const [findings, setFindings] = useState<Finding[]>([]);
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loadingResults, setLoadingResults] = useState(false);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

  const runAnalysis = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!owner || !repo || !prNumber) {
      setMessage("Please fill all fields.");
      return;
    }

    setLoading(true);
    setMessage("");

    try {
      const response = await fetch(
        `${apiUrl}/analyze?owner=${encodeURIComponent(owner)}&repo=${encodeURIComponent(repo)}&pr_number=${encodeURIComponent(
          Number(prNumber)
        )}`,
        { method: "POST" }
      );
      const data = await response.json();
      setMessage(data.message || "Analysis background task queued.");
    } catch (err) {
      console.error(err);
      setMessage("Failed to trigger analysis.");
    } finally {
      setLoading(false);
    }
  };

  const fetchResults = async () => {
    if (!owner || !repo || !prNumber) {
      setMessage("Owner/repo/pr required to fetch results");
      return;
    }

    setLoadingResults(true);
    setMessage("");

    try {
      const [findingsResp, reportResp] = await Promise.all([
        fetch(`${apiUrl}/findings?owner=${encodeURIComponent(owner)}&repo=${encodeURIComponent(repo)}&pr_number=${encodeURIComponent(Number(prNumber))}`),
        fetch(`${apiUrl}/reports/detail?owner=${encodeURIComponent(owner)}&repo=${encodeURIComponent(repo)}&pr_number=${encodeURIComponent(Number(prNumber))}`),
      ]);

      const findingsJson = await findingsResp.json();
      const reportJson = await reportResp.json();

      setFindings(findingsJson.findings || []);
      setReport(reportJson || null);

      if (!findingsJson.findings?.length && !reportJson) {
        setMessage("No data found for this PR yet. Wait a few seconds and retry.");
      }
    } catch (err) {
      console.error(err);
      setMessage("Error loading PR results.");
    } finally {
      setLoadingResults(false);
    }
  };

  useEffect(() => {
    // optionally keep data current after manual run.
  }, []);

  const agentGroups = findings.reduce<Record<string, Finding[]>>((acc, item) => {
    const key = item.agent_name || "unknown_agent";
    acc[key] = acc[key] || [];
    acc[key].push(item);
    return acc;
  }, {});

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="space-y-2">
        <h1 className="text-3xl font-extrabold tracking-tight">Testing Frontend Control Panel</h1>
        <p className="text-muted-foreground">Manual PR analysis with agent-context breakdown and findings insight.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <form onSubmit={runAnalysis} className="glass-card rounded-2xl p-6 space-y-4">
          <h2 className="font-bold text-xl">Trigger Analysis</h2>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <input
              type="text"
              placeholder="Owner"
              className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 focus:ring-2 focus:ring-primary outline-none"
              value={owner}
              onChange={(e) => setOwner(e.target.value)}
              required
            />
            <input
              type="text"
              placeholder="Repo"
              className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 focus:ring-2 focus:ring-primary outline-none"
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              required
            />
            <input
              type="number"
              placeholder="PR No."
              className="w-full bg-white/5 border border-white/10 rounded-xl px-3 py-2 focus:ring-2 focus:ring-primary outline-none"
              value={prNumber}
              onChange={(e) => setPrNumber(e.target.value)}
              required
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-primary hover:bg-primary/90 text-black font-bold py-3 rounded-xl transition-all disabled:opacity-50"
          >
            {loading ? "Triggering analysis..." : "Trigger PR Analysis"}
          </button>

          <button
            type="button"
            onClick={fetchResults}
            disabled={loadingResults}
            className="w-full bg-white/10 hover:bg-white/20 text-white font-semibold py-3 rounded-xl transition-all disabled:opacity-50"
          >
            {loadingResults ? "Loading results..." : "Fetch report + findings"}
          </button>

          {message && <div className="p-3 rounded bg-orange-100 text-orange-800 text-sm">{message}</div>}
        </form>

        <div className="glass-card rounded-2xl p-6 space-y-4">
          <h2 className="font-bold text-xl">Latest PR Snapshot</h2>
          {report ? (
            <div className="space-y-2 text-sm">
              <p><strong>PR</strong>: {owner}/{repo} #{prNumber}</p>
              <p><strong>Total Findings</strong>: {report.total_findings}</p>
              <p><strong>Confidence</strong>: {Math.round((report.avg_confidence || 0) * 100)}%</p>
              <p><strong>High/Med/Low</strong>: {report.high_count}/{report.medium_count}/{report.low_count}</p>
              <details className="bg-black/20 p-2 rounded">
                <summary className="font-semibold">Report Markdown</summary>
                <pre className="whitespace-pre-wrap text-xs mt-2">{report.report_markdown}</pre>
              </details>
            </div>
          ) : (
            <p className="text-muted-foreground">No report loaded. Click &quot;Fetch report + findings&quot; after analysis is queued.</p>
          )}
        </div>
      </div>

      <section className="space-y-4">
        <h2 className="font-bold text-xl">Agent Context Data</h2>

        {Object.keys(agentGroups).length ? (
          Object.entries(agentGroups).map(([agent, group]) => (
            <div key={agent} className="glass-card rounded-2xl p-4">
              <h3 className="font-semibold text-lg">{agent}</h3>
              <span className="text-xs text-muted-foreground">{group.length} findings</span>
              <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                {group.map((item) => (
                  <div key={item.id} className="border border-white/10 rounded p-3">
                    <p className="text-xs text-muted-foreground">{item.issue_type} - {item.severity}</p>
                    <p className="text-sm">{item.description}</p>
                    <details className="mt-2 text-xs text-muted-foreground">
                      <summary>Raw response payload</summary>
                      <pre className="whitespace-pre-wrap mt-1 text-[11px]">{item.raw_response}</pre>
                    </details>
                  </div>
                ))}
              </div>
            </div>
          ))
        ) : (
          <p className="text-muted-foreground">No findings loaded yet. Trigger analysis and refresh results.</p>
        )}
      </section>
    </div>
  );
}
