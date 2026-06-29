"use client";
import { useEffect, useState, useRef } from "react";
import {
  uploadDocument,
  getJobStatus,
  listDocuments,
  deleteDocument,
  Document,
} from "@/lib/api";
import { Upload, Trash2, CheckCircle, Clock, XCircle, Loader2 } from "lucide-react";

const DOC_TYPES = ["policy", "hr", "it", "sop", "compliance", "faq"];

const STATUS_BADGE: Record<string, { cls: string; label: string; icon: React.ReactNode }> = {
  active: { cls: "bg-green-900 text-green-300", label: "Active", icon: <CheckCircle size={11} /> },
  processing: {
    cls: "bg-blue-900 text-blue-300",
    label: "Processing",
    icon: <Loader2 size={11} className="animate-spin" />,
  },
  failed: { cls: "bg-red-900 text-red-300", label: "Failed", icon: <XCircle size={11} /> },
  archived: { cls: "bg-gray-800 text-gray-400", label: "Archived", icon: <Clock size={11} /> },
};

export default function DocumentsPage() {
  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState("policy");
  const [department, setDepartment] = useState("");
  const [uploading, setUploading] = useState(false);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [jobError, setJobError] = useState<string | null>(null);
  const [docs, setDocs] = useState<Document[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadDocs = () => listDocuments().then(setDocs).catch(console.error);
  useEffect(() => {
    loadDocs();
  }, []);

  // Clear any active poll on unmount to prevent leaks.
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setJobStatus("uploading");
    setJobError(null);
    try {
      const { job_id } = await uploadDocument(file, docType, department || undefined);
      setJobStatus("processing");
      pollRef.current = setInterval(async () => {
        try {
          const s = await getJobStatus(job_id);
          setJobStatus(s.status);
          if (s.status === "complete") {
            if (pollRef.current) clearInterval(pollRef.current);
            setUploading(false);
            setFile(null);
            if (fileRef.current) fileRef.current.value = "";
            loadDocs();
          } else if (s.status === "failed") {
            if (pollRef.current) clearInterval(pollRef.current);
            setJobError(s.error ?? "Ingestion failed");
            setUploading(false);
          }
        } catch {
          if (pollRef.current) clearInterval(pollRef.current);
          setUploading(false);
        }
      }, 2000);
    } catch (err: unknown) {
      setJobError(err instanceof Error ? err.message : "Upload failed");
      setUploading(false);
      setJobStatus(null);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Archive this document?")) return;
    await deleteDocument(id);
    loadDocs();
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-xl font-bold text-white mb-4">Documents</h1>
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-300 mb-4 flex items-center gap-2">
            <Upload size={14} /> Upload Document
          </h2>
          <form onSubmit={handleUpload} className="space-y-3">
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.docx,.html,.htm"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-gray-400 file:mr-3 file:py-1.5 file:px-3
                         file:rounded-lg file:border-0 file:bg-gray-700 file:text-gray-200
                         file:text-sm hover:file:bg-gray-600 cursor-pointer"
            />
            <div className="flex gap-3">
              <select
                value={docType}
                onChange={(e) => setDocType(e.target.value)}
                className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                           text-white text-sm focus:outline-none focus:border-blue-500"
              >
                {DOC_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <input
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                placeholder="Department (optional)"
                className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                           text-white text-sm placeholder-gray-500
                           focus:outline-none focus:border-blue-500"
              />
            </div>
            {jobStatus && (
              <div
                className={`text-sm px-3 py-2 rounded-lg ${
                  jobStatus === "complete"
                    ? "bg-green-900/30 text-green-300"
                    : jobStatus === "failed"
                      ? "bg-red-900/30 text-red-300"
                      : "bg-blue-900/30 text-blue-300"
                }`}
              >
                {jobStatus === "complete"
                  ? "✓ Indexed successfully"
                  : jobStatus === "failed"
                    ? `✗ ${jobError}`
                    : `Processing: ${jobStatus}…`}
              </div>
            )}
            <button
              type="submit"
              disabled={!file || uploading}
              className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40
                         text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              {uploading ? "Processing…" : "Upload & Index"}
            </button>
          </form>
        </div>
      </div>

      <div>
        <h2 className="text-sm font-semibold text-gray-300 mb-3">Indexed Documents</h2>
        <div className="space-y-2">
          {docs.length === 0 && <p className="text-gray-500 text-sm">No documents yet.</p>}
          {docs.map((doc) => {
            const badge = STATUS_BADGE[doc.status] ?? STATUS_BADGE.archived;
            return (
              <div
                key={doc.id}
                className="flex items-center justify-between bg-gray-900 border
                           border-gray-800 rounded-lg px-4 py-3"
              >
                <div className="min-w-0">
                  <div className="text-sm font-medium text-white truncate">{doc.filename}</div>
                  <div className="text-xs text-gray-500 mt-0.5">
                    {doc.doc_type} · v{doc.version}
                    {doc.page_count != null && ` · ${doc.page_count}p`}
                    {doc.department && ` · ${doc.department}`}
                    {" · "}
                    {new Date(doc.upload_date).toLocaleDateString()}
                  </div>
                </div>
                <div className="flex items-center gap-3 ml-4 shrink-0">
                  <span
                    className={`flex items-center gap-1 text-xs px-2 py-1 rounded-md ${badge.cls}`}
                  >
                    {badge.icon} {badge.label}
                  </span>
                  <button
                    onClick={() => handleDelete(doc.id)}
                    className="text-gray-600 hover:text-red-400 transition-colors"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
