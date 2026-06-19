"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import * as api from "@/lib/api";
import { docStatusClass, obligationClass, verdictClass } from "@/lib/ui";
import type {
  ComplianceEntry,
  DocumentT,
  Project,
  Requirement,
  Section,
} from "@/lib/types";

export default function ProjectWorkspace({
  params,
}: {
  params: { id: string };
}) {
  const pid = params.id;
  const router = useRouter();

  const [project, setProject] = useState<Project | null>(null);
  const [documents, setDocuments] = useState<DocumentT[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [compliance, setCompliance] = useState<ComplianceEntry[]>([]);
  const [sections, setSections] = useState<Section[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});

  const [kind, setKind] = useState("internal");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState<string>("");
  const [err, setErr] = useState("");
  const [ready, setReady] = useState(false);

  const refreshDocs = useCallback(async () => {
    setDocuments(await api.listDocuments());
  }, []);

  const refreshAll = useCallback(async () => {
    const [p, d, r, c, s] = await Promise.all([
      api.getProject(pid),
      api.listDocuments(),
      api.listRequirements(pid),
      api.getCompliance(pid),
      api.listSections(pid),
    ]);
    setProject(p);
    setDocuments(d);
    setRequirements(r);
    setCompliance(c);
    setSections(s);
  }, [pid]);

  useEffect(() => {
    if (!api.getToken()) {
      router.replace("/login");
      return;
    }
    setReady(true);
    refreshAll().catch((e) =>
      setErr(e instanceof Error ? e.message : "Erreur"),
    );
  }, [router, refreshAll]);

  // Auto-rafraîchit tant qu'un document est en cours d'ingestion.
  useEffect(() => {
    if (documents.some((d) => d.status === "pending" || d.status === "processing")) {
      const t = setTimeout(() => {
        refreshDocs().catch(() => {});
      }, 3000);
      return () => clearTimeout(t);
    }
  }, [documents, refreshDocs]);

  async function run(label: string, fn: () => Promise<void>) {
    setErr("");
    setBusy(label);
    try {
      await fn();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Erreur");
    } finally {
      setBusy("");
    }
  }

  const onUpload = (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    run("upload", async () => {
      await api.uploadDocument(file, kind, pid);
      setFile(null);
      (document.getElementById("file-input") as HTMLInputElement).value = "";
      await refreshDocs();
    });
  };

  const tenderDocs = documents.filter((d) => d.kind === "tender");

  if (!ready) return null;

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-6">
      <header className="flex items-center justify-between">
        <div>
          <Link href="/projects" className="text-sm text-slate-500 hover:text-slate-700">
            ← Mes projets
          </Link>
          <h1 className="text-2xl font-bold">{project?.name ?? "…"}</h1>
          {project?.buyer_name && (
            <p className="text-sm text-slate-500">{project.buyer_name}</p>
          )}
        </div>
      </header>

      {err && (
        <div className="rounded-lg bg-red-50 px-4 py-2 text-sm text-red-700">
          {err}
        </div>
      )}

      {/* 1. Documents */}
      <Card
        step="1"
        title="Documents"
        subtitle="Charge l'appel d'offres (tender) et ta base documentaire interne (internal)."
      >
        <form onSubmit={onUpload} className="flex flex-wrap items-center gap-2">
          <input
            id="file-input"
            type="file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="text-sm"
          />
          <select
            value={kind}
            onChange={(e) => setKind(e.target.value)}
            className="rounded-lg border border-slate-300 px-2 py-2 text-sm"
          >
            <option value="internal">Base interne</option>
            <option value="tender">Appel d'offres</option>
          </select>
          <button
            disabled={busy === "upload" || !file}
            className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {busy === "upload" ? "Envoi…" : "Uploader"}
          </button>
        </form>

        <ul className="mt-4 space-y-2">
          {documents.map((d) => (
            <li
              key={d.id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 p-3 text-sm"
            >
              <div className="flex items-center gap-2">
                <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                  {d.kind}
                </span>
                <span className="font-medium">{d.filename}</span>
                <span
                  className={`rounded px-2 py-0.5 text-xs ${docStatusClass(d.status)}`}
                >
                  {d.status}
                  {d.status === "ready" ? ` · ${d.chunk_count} extraits` : ""}
                </span>
              </div>
              {d.kind === "tender" && (
                <button
                  disabled={!!busy}
                  onClick={() =>
                    run("extract", async () => {
                      setRequirements(await api.extractRequirements(pid, d.id));
                    })
                  }
                  className="rounded-lg border border-slate-300 px-3 py-1 text-xs font-medium hover:bg-slate-50 disabled:opacity-50"
                >
                  {busy === "extract" ? "Extraction…" : "Extraire les exigences"}
                </button>
              )}
            </li>
          ))}
          {documents.length === 0 && (
            <li className="text-sm text-slate-400">Aucun document.</li>
          )}
        </ul>
        {!documents.some((d) => d.kind === "internal" && d.status === "ready") && (
          <p className="mt-3 text-xs text-amber-600">
            ⚠️ Sans base interne « ready », les exigences ressortiront « manquant »
            et les réponses seront [À compléter] (le moteur n'invente jamais).
          </p>
        )}
      </Card>

      {/* 2. Exigences */}
      <Card
        step="2"
        title="Exigences"
        subtitle="Extraites de l'AO. Valide ou rejette pour la revue."
      >
        {requirements.length === 0 ? (
          <p className="text-sm text-slate-400">
            {tenderDocs.length === 0
              ? "Charge un appel d'offres puis clique « Extraire les exigences »."
              : "Aucune exigence extraite pour l'instant."}
          </p>
        ) : (
          <ul className="space-y-2">
            {requirements.map((r) => (
              <li
                key={r.id}
                className="rounded-lg border border-slate-200 p-3 text-sm"
              >
                <div className="flex flex-wrap items-center gap-2">
                  {r.code && (
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                      {r.code}
                    </span>
                  )}
                  <span
                    className={`rounded px-2 py-0.5 text-xs ${obligationClass(r.obligation)}`}
                  >
                    {r.obligation}
                  </span>
                  {r.category && (
                    <span className="text-xs text-slate-400">{r.category}</span>
                  )}
                  <span className="ml-auto text-xs text-slate-400">{r.status}</span>
                </div>
                <p className="mt-1">{r.text}</p>
                <div className="mt-2 flex gap-2">
                  <button
                    disabled={!!busy}
                    onClick={() =>
                      run("req", async () => {
                        await api.updateRequirement(pid, r.id, {
                          status: "validated",
                        });
                        setRequirements(await api.listRequirements(pid));
                      })
                    }
                    className="rounded border border-green-300 px-2 py-1 text-xs text-green-700 hover:bg-green-50"
                  >
                    Valider
                  </button>
                  <button
                    disabled={!!busy}
                    onClick={() =>
                      run("req", async () => {
                        await api.updateRequirement(pid, r.id, {
                          status: "rejected",
                        });
                        setRequirements(await api.listRequirements(pid));
                      })
                    }
                    className="rounded border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50"
                  >
                    Rejeter
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* 3. Matrice de conformité */}
      <Card
        step="3"
        title="Matrice de conformité"
        subtitle="Pour chaque exigence : preuve dans ta base interne ou « manquant »."
        action={
          <button
            disabled={!!busy || requirements.length === 0}
            onClick={() =>
              run("compliance", async () => {
                setCompliance(await api.buildCompliance(pid));
              })
            }
            className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {busy === "compliance" ? "Analyse…" : "Construire la matrice"}
          </button>
        }
      >
        {compliance.length === 0 ? (
          <p className="text-sm text-slate-400">
            Pas encore d'analyse. Clique « Construire la matrice ».
          </p>
        ) : (
          <ul className="space-y-2">
            {compliance.map((c) => (
              <li
                key={c.id}
                className="rounded-lg border border-slate-200 p-3 text-sm"
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-medium ${verdictClass(c.verdict)}`}
                  >
                    {c.verdict}
                  </span>
                  <span className="font-medium">{c.requirement_text}</span>
                </div>
                {c.rationale && (
                  <p className="mt-1 text-slate-600">{c.rationale}</p>
                )}
                {c.sources.length > 0 && (
                  <p className="mt-1 text-xs text-slate-400">
                    Sources : {c.sources.map((s) => s.filename).join(", ")}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* 4. Réponse */}
      <Card
        step="4"
        title="Réponse"
        subtitle="Sections rédigées depuis tes preuves internes. [À compléter] = non couvert."
        action={
          <div className="flex gap-2">
            <button
              disabled={!!busy || requirements.length === 0}
              onClick={() =>
                run("sections", async () => {
                  const s = await api.generateSections(pid);
                  setSections(s);
                  setDrafts({});
                })
              }
              className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {busy === "sections" ? "Rédaction…" : "Générer les sections"}
            </button>
            <button
              disabled={!!busy || sections.length === 0}
              onClick={() =>
                run("export", () =>
                  api.exportDocx(pid, project?.name ?? "reponse"),
                )
              }
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium hover:bg-slate-50 disabled:opacity-50"
            >
              Exporter en Word
            </button>
          </div>
        }
      >
        {sections.length === 0 ? (
          <p className="text-sm text-slate-400">
            Pas encore de réponse. Clique « Générer les sections ».
          </p>
        ) : (
          <ul className="space-y-4">
            {sections.map((s) => {
              const value = drafts[s.id] ?? s.content;
              const dirty = drafts[s.id] !== undefined && drafts[s.id] !== s.content;
              return (
                <li key={s.id}>
                  <div className="mb-1 flex items-center gap-2">
                    <span className="text-sm font-medium">{s.title}</span>
                    <span className="text-xs text-slate-400">{s.status}</span>
                  </div>
                  <textarea
                    value={value}
                    onChange={(e) =>
                      setDrafts((d) => ({ ...d, [s.id]: e.target.value }))
                    }
                    rows={4}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                  />
                  {dirty && (
                    <button
                      disabled={!!busy}
                      onClick={() =>
                        run("save", async () => {
                          await api.updateSection(pid, s.requirement_id, {
                            content: value,
                          });
                          setSections(await api.listSections(pid));
                          setDrafts((d) => {
                            const n = { ...d };
                            delete n[s.id];
                            return n;
                          });
                        })
                      }
                      className="mt-1 rounded-lg bg-slate-900 px-3 py-1 text-xs font-medium text-white hover:bg-slate-800"
                    >
                      Enregistrer
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </main>
  );
}

function Card({
  step,
  title,
  subtitle,
  action,
  children,
}: {
  step: string;
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-900 text-sm font-semibold text-white">
            {step}
          </span>
          <div>
            <h2 className="font-semibold">{title}</h2>
            {subtitle && <p className="text-sm text-slate-500">{subtitle}</p>}
          </div>
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
