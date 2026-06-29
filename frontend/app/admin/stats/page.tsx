"use client";
import { useEffect, useState } from "react";
import { getStats, Stats } from "@/lib/api";
import { StatCard } from "@/components/StatCard";
import { Activity, FileText, Layers, AlertCircle, Clock, XCircle } from "lucide-react";

const CARDS = [
  { key: "total_queries", label: "Total Queries", icon: Activity, color: "blue" },
  { key: "total_documents", label: "Active Documents", icon: FileText, color: "green" },
  { key: "total_chunks", label: "Indexed Chunks", icon: Layers, color: "purple" },
  { key: "open_escalations", label: "Open Escalations", icon: AlertCircle, color: "amber" },
  { key: "refusal_rate_pct", label: "Refusal Rate (%)", icon: XCircle, color: "red" },
  { key: "avg_latency_ms", label: "Avg Latency (ms)", icon: Clock, color: "gray" },
] as const;

export default function StatsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getStats()
      .then(setStats)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div>
      <h1 className="text-xl font-bold text-white mb-6">System Dashboard</h1>
      {error && <p className="text-red-400 mb-4">{error}</p>}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        {CARDS.map(({ key, label, icon, color }) => (
          <StatCard
            key={key}
            label={label}
            icon={icon}
            color={color}
            value={stats ? String(stats[key]) : "—"}
          />
        ))}
      </div>
    </div>
  );
}
