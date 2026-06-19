"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { clearToken, createProject, getToken, listProjects } from "@/lib/api";
import type { Project } from "@/lib/types";

export default function ProjectsPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [buyer, setBuyer] = useState("");
  const [err, setErr] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setReady(true);
    refresh();
  }, [router]);

  async function refresh() {
    try {
      setProjects(await listProjects());
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Erreur");
    }
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await createProject(name, buyer || undefined);
      setName("");
      setBuyer("");
      refresh();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Erreur");
    }
  }

  function logout() {
    clearToken();
    router.replace("/login");
  }

  if (!ready) return null;

  return (
    <main className="mx-auto max-w-4xl p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Mes appels d'offres</h1>
        <button
          onClick={logout}
          className="text-sm text-slate-500 hover:text-slate-700"
        >
          Déconnexion
        </button>
      </header>

      <form
        onSubmit={add}
        className="mt-6 flex flex-wrap gap-2 rounded-xl border border-slate-200 bg-white p-4"
      >
        <input
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          placeholder="Nom du projet (ex. AO Mairie de X)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <input
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          placeholder="Acheteur (optionnel)"
          value={buyer}
          onChange={(e) => setBuyer(e.target.value)}
        />
        <button className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800">
          Nouveau projet
        </button>
      </form>

      {err && <p className="mt-3 text-sm text-red-600">{err}</p>}

      <ul className="mt-6 space-y-2">
        {projects.length === 0 && (
          <li className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-slate-400">
            Aucun projet pour l'instant. Crée ton premier appel d'offres ci-dessus.
          </li>
        )}
        {projects.map((p) => (
          <li key={p.id}>
            <Link
              href={`/projects/${p.id}`}
              className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4 hover:border-slate-400"
            >
              <div>
                <div className="font-medium">{p.name}</div>
                <div className="text-sm text-slate-500">
                  {p.buyer_name || "—"}
                </div>
              </div>
              <span className="text-slate-400">→</span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
