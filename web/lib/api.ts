import type {
  ComplianceEntry,
  DocumentT,
  Project,
  Requirement,
  Section,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8010";
const TOKEN_KEY = "ao_token";

export function getToken(): string | null {
  return typeof window !== "undefined" ? localStorage.getItem(TOKEN_KEY) : null;
}
export function setToken(t: string): void {
  localStorage.setItem(TOKEN_KEY, t);
}
export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

async function check(res: Response): Promise<Response> {
  if (!res.ok) {
    let detail = `Erreur ${res.status}`;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* corps non-JSON */
    }
    throw new Error(detail);
  }
  return res;
}

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

async function jget<T>(path: string): Promise<T> {
  const res = await check(await fetch(`${BASE}${path}`, { headers: authHeaders() }));
  return res.json() as Promise<T>;
}

async function jsend<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await check(
    await fetch(`${BASE}${path}`, {
      method,
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// --- auth ---
export async function register(
  email: string,
  password: string,
  org_name: string,
): Promise<void> {
  await jsend("/auth/register", "POST", { email, password, org_name });
}

export async function login(email: string, password: string): Promise<void> {
  const body = new URLSearchParams({ username: email, password });
  const res = await check(
    await fetch(`${BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    }),
  );
  const data = await res.json();
  setToken(data.access_token);
}

// --- projects ---
export const listProjects = () => jget<Project[]>("/projects");
export const getProject = (id: string) => jget<Project>(`/projects/${id}`);
export const createProject = (name: string, buyer_name?: string) =>
  jsend<Project>("/projects", "POST", { name, buyer_name });

// --- documents ---
export const listDocuments = () => jget<DocumentT[]>("/documents");
export async function uploadDocument(
  file: File,
  kind: string,
  projectId?: string,
): Promise<DocumentT> {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("kind", kind);
  if (projectId) fd.append("project_id", projectId);
  const res = await check(
    await fetch(`${BASE}/documents/upload`, {
      method: "POST",
      headers: authHeaders(),
      body: fd,
    }),
  );
  return res.json();
}

// --- requirements ---
export const extractRequirements = (pid: string, document_id: string) =>
  jsend<Requirement[]>(`/projects/${pid}/requirements/extract`, "POST", {
    document_id,
  });
export const listRequirements = (pid: string) =>
  jget<Requirement[]>(`/projects/${pid}/requirements`);
export const updateRequirement = (
  pid: string,
  rid: string,
  patch: Partial<Requirement>,
) => jsend<Requirement>(`/projects/${pid}/requirements/${rid}`, "PATCH", patch);

// --- compliance ---
export const buildCompliance = (pid: string) =>
  jsend<ComplianceEntry[]>(`/projects/${pid}/compliance/build`, "POST");
export const getCompliance = (pid: string) =>
  jget<ComplianceEntry[]>(`/projects/${pid}/compliance`);

// --- sections ---
export const generateSections = (pid: string) =>
  jsend<Section[]>(`/projects/${pid}/sections/generate`, "POST");
export const listSections = (pid: string) =>
  jget<Section[]>(`/projects/${pid}/sections`);
export const updateSection = (pid: string, rid: string, patch: Partial<Section>) =>
  jsend<Section>(`/projects/${pid}/sections/${rid}`, "PATCH", patch);

export async function exportDocx(pid: string, projectName: string): Promise<void> {
  const res = await check(
    await fetch(`${BASE}/projects/${pid}/sections/export`, {
      headers: authHeaders(),
    }),
  );
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `reponse_${projectName || pid}.docx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
