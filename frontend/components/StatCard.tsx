import type { LucideIcon } from "lucide-react";

const COLOR_MAP: Record<string, string> = {
  blue: "bg-blue-900/40 text-blue-300 border-blue-800",
  green: "bg-green-900/40 text-green-300 border-green-800",
  purple: "bg-purple-900/40 text-purple-300 border-purple-800",
  amber: "bg-amber-900/40 text-amber-300 border-amber-800",
  red: "bg-red-900/40 text-red-300 border-red-800",
  gray: "bg-gray-800/40 text-gray-300 border-gray-700",
};

export function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string;
  value: string;
  icon: LucideIcon;
  color: string;
}) {
  return (
    <div className={`border rounded-xl p-4 ${COLOR_MAP[color] ?? COLOR_MAP.gray}`}>
      <div className="flex items-center gap-2 mb-2">
        <Icon size={15} />
        <span className="text-xs font-medium uppercase tracking-wide opacity-70">{label}</span>
      </div>
      <div className="text-3xl font-bold text-white">{value}</div>
    </div>
  );
}
