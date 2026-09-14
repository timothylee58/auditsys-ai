const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// TODO: replace with a real authenticated user id once an auth layer
// exists. Until then, every request identifies as this single demo user
// so the backend's X-User-ID / reviewer_user_id-scoped endpoints
// (documents, query status polling, review queue) have something
// consistent to filter and write against.
const DEMO_USER_ID = process.env.NEXT_PUBLIC_DEMO_USER_ID ?? "demo-user";

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Accept: "application/json", "X-User-ID": DEMO_USER_ID },
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json", "X-User-ID": DEMO_USER_ID },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "X-User-ID": DEMO_USER_ID },
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export { API_BASE_URL, DEMO_USER_ID };
