import { FileText } from "lucide-react";
import type { Citation } from "@/lib/api";

export function CitationCard({ citation }: { citation: Citation }) {
  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg px-3 py-2">
      <div className="flex items-start gap-2">
        <FileText size={13} className="text-blue-400 mt-0.5 shrink-0" />
        <div className="min-w-0">
          <div className="text-xs font-medium text-blue-300 truncate">{citation.filename}</div>
          <div className="text-xs text-gray-500 mt-0.5">
            {[
              citation.page_number != null && `Page ${citation.page_number}`,
              citation.section && `§ ${citation.section}`,
            ]
              .filter(Boolean)
              .join(" · ")}
          </div>
          <p className="text-xs text-gray-300 mt-1 line-clamp-3">{citation.excerpt}</p>
        </div>
        <span className="text-xs bg-gray-700 text-gray-300 rounded px-1.5 py-0.5 shrink-0 font-mono">
          [{citation.source_num}]
        </span>
      </div>
    </div>
  );
}
