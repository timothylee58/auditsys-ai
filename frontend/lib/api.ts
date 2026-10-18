import { getAccessToken } from "@/lib/supabase";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

/**
 * Build request headers including the Supabase bearer token. The backend
 * derives identity exclusively from the verified JWT — it no longer accepts
 * a self-asserted X-User-ID header.
 */
export async function authHeaders(
  extra: Record<string, string> = {}
): Promise<Record<string, string>> {
  const headers: Record<string, string> = { Accept: "application/json", ...extra };
  const token = await getAccessToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function raiseForStatus(response: Response): Promise<never> {
  let detail = `API request failed: ${response.status}`;
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (body?.detail) {
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    }
  } catch {
    // body wasn't JSON — keep the generic message
  }
  if (response.status === 401) {
    detail = "Your session has expired — please sign in again.";
  }
  throw new ApiError(detail, response.status);
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: await authHeaders(),
    cache: "no-store"
  });

  if (!response.ok) {
    await raiseForStatus(response);
  }

  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: await authHeaders({ "Content-Type": "application/json" }),
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store"
  });

  if (!response.ok) {
    await raiseForStatus(response);
  }

  return response.json() as Promise<T>;
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: await authHeaders(),
    body: formData
  });

  if (!response.ok) {
    await raiseForStatus(response);
  }

  return response.json() as Promise<T>;
}

export { API_BASE_URL };
