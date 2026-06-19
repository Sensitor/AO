"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(getToken() ? "/projects" : "/login");
  }, [router]);
  return (
    <main className="flex min-h-screen items-center justify-center text-slate-500">
      Chargement…
    </main>
  );
}
