import type { Job, ProviderInfo } from "./types";

/** Thrown for any non-2xx response. Carries the HTTP status so callers
 * (the job poller in particular) can distinguish a transient network blip
 * from a definitive 404 without parsing message text. */
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function check(res: Response): Promise<Response> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* keep default detail */
    }
    throw new ApiError(res.status, detail);
  }
  return res;
}

export async function fetchProviders(): Promise<ProviderInfo[]> {
  return (await check(await fetch("/api/providers"))).json();
}

export async function startExtraction(file: File, refresh = false, documentFormat = "auto"): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  form.append("refresh", String(refresh));
  form.append("document_format", documentFormat);
  const res = await check(
    await fetch("/api/extract", { method: "POST", body: form })
  );
  return (await res.json()).job_id;
}

export interface ResearchParams {
  extract_job_id: string;
  reuse_existing?: boolean;
  research_prompt?: string;
  provider: string;
  model?: string;
  tier: string;
  formats: string[];
}

export async function startResearch(params: ResearchParams): Promise<string> {
  const res = await check(
    await fetch("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    })
  );
  return (await res.json()).job_id;
}

export async function fetchJob(jobId: string): Promise<Job> {
  return (await check(await fetch(`/api/jobs/${jobId}`))).json();
}

export function fileUrl(jobId: string, kind: "pdf" | "md" | "json"): string {
  return `/api/jobs/${jobId}/files/${kind}`;
}

export interface LibraryRun {
  id: string;
  created_at: string;
  organization: string;
  project_title: string;
  country: string;
  provider: string;
  model: string;
}

export async function fetchLibrary(query = ""): Promise<LibraryRun[]> {
  return (await check(await fetch(`/api/library?q=${encodeURIComponent(query)}`))).json();
}
