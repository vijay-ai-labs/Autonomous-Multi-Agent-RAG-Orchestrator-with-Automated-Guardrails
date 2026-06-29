"use client";
import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { getAuth, clearAuth } from "@/lib/auth";
import { LayoutDashboard, FileText, AlertCircle, LogOut } from "lucide-react";

const NAV = [
  { href: "/admin/stats", label: "Dashboard", icon: LayoutDashboard },
  { href: "/admin/documents", label: "Documents", icon: FileText },
  { href: "/admin/escalations", label: "Escalations", icon: AlertCircle },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const auth = getAuth();

  useEffect(() => {
    if (!auth) {
      router.replace("/login");
      return;
    }
    if (auth.role !== "admin") {
      router.replace("/chat");
    }
  }, [auth, router]);

  if (!auth) return null;

  return (
    <div className="flex h-screen bg-gray-950">
      {/* Sidebar */}
      <aside className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col">
        <div className="px-4 py-5 border-b border-gray-800">
          <div className="font-bold text-white text-sm">RAG Orchestrator</div>
          <div className="text-xs text-gray-500 mt-0.5">Admin Panel</div>
        </div>
        <nav className="flex-1 px-2 py-4 space-y-1">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                pathname.startsWith(href)
                  ? "bg-blue-600 text-white"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`}
            >
              <Icon size={15} />
              {label}
            </Link>
          ))}
        </nav>
        <div className="px-2 pb-4">
          <button
            onClick={() => {
              clearAuth();
              router.replace("/login");
            }}
            className="flex items-center gap-2.5 px-3 py-2 w-full rounded-lg text-sm
                       text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
          >
            <LogOut size={15} /> Sign out
          </button>
        </div>
      </aside>

      {/* Content */}
      <main className="flex-1 overflow-y-auto p-6">{children}</main>
    </div>
  );
}
