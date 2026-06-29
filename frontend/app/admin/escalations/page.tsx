"use client";
import { useEffect, useState } from "react";
import { listEscalations, updateEscalation, Escalation } from "@/lib/api";
import { Clock, User } from "lucide-react";

const STATUS_COLOR: Record<string, string> = {
  open: "bg-red-900 text-red-300",
  in_progress: "bg-amber-900 text-amber-300",
  resolved: "bg-green-900 text-green-300",
};

export default function EscalationsPage() {
  const [items, setItems] = useState<Escalation[]>([]);
  const [filter, setFilter] = useState("open");
  const [resolving, setResolving] = useState<string | null>(null);

  const load = () => listEscalations(filter).then(setItems).catch(console.error);
  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter]);

  async function resolve(id: string) {
    const notes = prompt("Resolution notes (optional):");
    if (notes === null) return;
    setResolving(id);
    try {
      await updateEscalation(id, { status: "resolved", resolution_notes: notes || undefined });
      load();
    } finally {
      setResolving(null);
    }
  }

  async function assign(id: string) {
    const assignee = prompt("Assign to (email or team):");
    if (!assignee) return;
    await updateEscalation(id, { status: "in_progress", assigned_to: assignee });
    load();
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold text-white">Escalation Queue</h1>
        <div className="flex gap-2">
          {["open", "in_progress", "resolved"].map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`text-xs px-3 py-1.5 rounded-lg transition-colors ${
                filter === s ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-400 hover:text-white"
              }`}
            >
              {s.replace("_", " ")}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        {items.length === 0 && (
          <p className="text-gray-500 text-sm">No {filter.replace("_", " ")} escalations.</p>
        )}
        {items.map((item) => (
          <div key={item.id} className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span
                    className={`text-xs px-2 py-0.5 rounded font-medium ${STATUS_COLOR[item.status] ?? "bg-gray-800 text-gray-400"}`}
                  >
                    {item.status.replace("_", " ")}
                  </span>
                  <span className="text-xs text-gray-500 font-mono">
                    #{item.id.slice(0, 8).toUpperCase()}
                  </span>
                  <span className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded">
                    {item.reason_code.replace(/_/g, " ")}
                  </span>
                </div>
                <div className="text-xs text-gray-500 mt-2 flex items-center gap-3">
                  <span>
                    <Clock size={10} className="inline mr-1" />
                    {new Date(item.created_at).toLocaleString()}
                  </span>
                  {item.assigned_to && (
                    <span>
                      <User size={10} className="inline mr-1" />
                      {item.assigned_to}
                    </span>
                  )}
                </div>
                {item.resolution_notes && (
                  <p className="text-xs text-gray-400 mt-1 italic">{item.resolution_notes}</p>
                )}
              </div>
              {item.status !== "resolved" && (
                <div className="flex gap-2 shrink-0">
                  {item.status === "open" && (
                    <button
                      onClick={() => assign(item.id)}
                      className="text-xs bg-gray-800 hover:bg-gray-700 text-gray-300
                                 px-3 py-1.5 rounded-lg transition-colors"
                    >
                      Assign
                    </button>
                  )}
                  <button
                    onClick={() => resolve(item.id)}
                    disabled={resolving === item.id}
                    className="text-xs bg-green-800 hover:bg-green-700 text-green-200
                               px-3 py-1.5 rounded-lg transition-colors disabled:opacity-40"
                  >
                    {resolving === item.id ? "…" : "Resolve"}
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
