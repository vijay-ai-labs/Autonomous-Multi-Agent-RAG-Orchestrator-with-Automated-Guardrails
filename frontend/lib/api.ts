const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

// Auth
export const login = (email: string, password: string) =>
  request<{ access_token: string; user_id: string; email: string; role: string }>(
    "/auth/login",
    { method: "POST", body: JSON.stringify({ email, password }) }
  );

export const register = (email: string, password: string, role = "employee") =>
  request<{ access_token: string; user_id: string; email: string; role: string }>(
    "/auth/register",
    { method: "POST", body: JSON.stringify({ email, password, role }) }
  );

// Query
export type Citation = {
  source_num: number;
  filename: string;
  page_number: number | null;
  section: string | null;
  excerpt: string;
  document_id: string;
};

export type QueryResponse = {
  query_id: string;
  session_id: string;
  answer: string;
  citations: Citation[];
  confidence: number;
  refused: boolean;
  refusal_reason: string | null;
};

export const sendQuery = (query: string, session_id?: string) =>
  request<QueryResponse>("/query", {
    method: "POST",
    body: JSON.stringify({ query, session_id: session_id ?? null }),
  });

// Documents
export type Document = {
  id: string;
  filename: string;
  doc_type: string;
  department: string | null;
  status: string;
  upload_date: string;
  version: number;
  page_count: number | null;
};

export const listDocuments = (doc_type?: string) =>
  request<Document[]>(`/documents${doc_type ? `?doc_type=${doc_type}` : ""}`);

export const deleteDocument = (id: string) =>
  fetch(`${BASE}/documents/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${getToken()}` },
  });

export const uploadDocument = async (
  file: File,
  doc_type: string,
  department?: string
): Promise<{ job_id: string; document_id: string }> => {
  const form = new FormData();
  form.append("file", file);
  form.append("doc_type", doc_type);
  if (department) form.append("department", department);
  const token = getToken();
  const res = await fetch(`${BASE}/ingest`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
};

export const getJobStatus = (job_id: string) =>
  request<{ job_id: string; status: string; chunk_count?: number; error?: string }>(
    `/ingest/${job_id}/status`
  );

// Escalations
export type Escalation = {
  id: string;
  query_id: string;
  reason_code: string;
  status: string;
  assigned_to: string | null;
  created_at: string;
  resolved_at: string | null;
  resolution_notes: string | null;
};

export const listEscalations = (status?: string) =>
  request<Escalation[]>(`/escalations${status ? `?status=${status}` : ""}`);

export const updateEscalation = (
  id: string,
  body: { status: string; assigned_to?: string; resolution_notes?: string }
) => request(`/escalations/${id}`, { method: "PATCH", body: JSON.stringify(body) });

// Stats
export type Stats = {
  total_queries: number;
  total_documents: number;
  total_chunks: number;
  open_escalations: number;
  refusal_rate_pct: number;
  avg_latency_ms: number;
};

export const getStats = () => request<Stats>("/stats");
