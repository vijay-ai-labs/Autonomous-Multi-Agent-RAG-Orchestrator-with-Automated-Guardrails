"use client";
import { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { sendQuery, Citation } from "@/lib/api";
import { getAuth, clearAuth } from "@/lib/auth";
import { CitationCard } from "@/components/CitationCard";
import { ChevronDown, ChevronUp, Send, LogOut, AlertTriangle } from "lucide-react";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  confidence?: number;
  refused?: boolean;
  refusal_reason?: string | null;
};

export default function ChatPage() {
  const router = useRouter();
  const auth = getAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!auth) {
      router.replace("/login");
      return;
    }
  }, [auth, router]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    setMessages((m) => [...m, { id: Date.now().toString(), role: "user", content: text }]);
    setLoading(true);
    try {
      const res = await sendQuery(text, sessionId);
      setSessionId(res.session_id);
      setMessages((m) => [
        ...m,
        {
          id: res.query_id,
          role: "assistant",
          content: res.answer,
          citations: res.citations,
          confidence: res.confidence,
          refused: res.refused,
          refusal_reason: res.refusal_reason,
        },
      ]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Request failed";
      setMessages((m) => [
        ...m,
        { id: Date.now().toString(), role: "assistant", content: `Error: ${msg}`, refused: true },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function logout() {
    clearAuth();
    router.replace("/login");
  }

  if (!auth) return null;

  return (
    <div className="flex flex-col h-screen bg-gray-950">
      {/* Navbar */}
      <nav className="flex items-center justify-between px-6 py-3 bg-gray-900 border-b border-gray-800">
        <div className="font-semibold text-white">Internal AI Assistant</div>
        <div className="flex items-center gap-3">
          <span className="text-gray-400 text-sm">{auth.email}</span>
          {auth.role === "admin" && (
            <a
              href="/admin/stats"
              className="text-sm text-blue-400 hover:text-blue-300 transition-colors"
            >
              Admin
            </a>
          )}
          <button
            onClick={logout}
            className="text-gray-400 hover:text-gray-200 transition-colors"
          >
            <LogOut size={16} />
          </button>
        </div>
      </nav>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-500 mt-20">
            <div className="text-4xl mb-4">💬</div>
            <div className="text-lg font-medium text-gray-400">
              Ask anything about company policies
            </div>
            <div className="text-sm mt-2">
              I answer based on approved company documents and always cite my sources.
            </div>
          </div>
        )}
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {loading && (
          <div className="flex gap-2 items-center text-gray-400 text-sm pl-2">
            <span className="inline-flex gap-1">
              <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce [animation-delay:0ms]" />
              <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce [animation-delay:150ms]" />
              <span className="w-2 h-2 bg-gray-500 rounded-full animate-bounce [animation-delay:300ms]" />
            </span>
            Searching documents…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-4 pb-4">
        <form onSubmit={handleSend} className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about company policies, benefits, IT support…"
            disabled={loading}
            className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-3
                       text-white placeholder-gray-500 focus:outline-none focus:border-blue-500
                       disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white
                       rounded-xl px-4 py-3 transition-colors"
          >
            <Send size={18} />
          </button>
        </form>
        <p className="text-xs text-gray-600 mt-2 text-center">
          Answers are grounded in approved company documents. Always verify with HR/IT for
          critical decisions.
        </p>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const [showCitations, setShowCitations] = useState(false);
  const isUser = message.role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-2xl w-full ${isUser ? "pl-16" : "pr-16"}`}>
        <div
          className={`rounded-2xl px-4 py-3 ${
            isUser
              ? "bg-blue-600 text-white ml-auto"
              : message.refused
                ? "bg-amber-950 border border-amber-800 text-amber-100"
                : "bg-gray-800 text-gray-100"
          }`}
        >
          {message.refused && (
            <div className="flex items-center gap-2 text-amber-400 text-xs font-medium mb-2">
              <AlertTriangle size={12} /> Unable to answer from documents
            </div>
          )}
          <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.content}</p>
          {!isUser && message.confidence !== undefined && !message.refused && (
            <div className="mt-2 text-xs text-gray-500">
              Confidence: {Math.round(message.confidence * 100)}%
            </div>
          )}
        </div>

        {/* Citations */}
        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="mt-2">
            <button
              onClick={() => setShowCitations((v) => !v)}
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200
                         transition-colors px-2"
            >
              {showCitations ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              {message.citations.length} source{message.citations.length > 1 ? "s" : ""}
            </button>
            {showCitations && (
              <div className="mt-2 space-y-2">
                {message.citations.map((c) => (
                  <CitationCard key={c.source_num} citation={c} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
