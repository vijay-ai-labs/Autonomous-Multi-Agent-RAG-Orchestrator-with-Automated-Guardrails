"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getAuth } from "@/lib/auth";

export default function Root() {
  const router = useRouter();
  useEffect(() => {
    const user = getAuth();
    if (!user) {
      router.replace("/login");
      return;
    }
    router.replace(user.role === "admin" ? "/admin/stats" : "/chat");
  }, [router]);
  return null;
}
