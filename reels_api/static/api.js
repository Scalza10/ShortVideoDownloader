// Every request goes through api(): a 401 anywhere means the session cookie is gone.
export class Unauthorized extends Error {}

export async function api(path, options) {
  const response = await fetch(path, options);
  if (response.status === 401) {
    location.reload();
    throw new Unauthorized();
  }
  return response;
}

// Deletes this phone's login cookie (cookie spec 5.3). A 401 means it is already gone; api() reloads.
export async function logout() {
  const response = await api("/web/logout", { method: "POST" });
  if (!response.ok) throw new Error(`POST /web/logout failed: ${response.status}`);
}

// Marks this phone's login cookie as agreed (pop-up spec 5.2). A 401 means it is already gone; api() reloads.
export async function agreeToCookie() {
  const response = await api("/web/cookie", { method: "POST" });
  if (!response.ok) throw new Error(`POST /web/cookie failed: ${response.status}`);
}

export async function listJobs() {
  const response = await api("/jobs");
  if (!response.ok) throw new Error(`GET /jobs failed: ${response.status}`);
  const body = await response.json();
  return body.jobs || [];
}

// The job, or null when the server does not know the id.
export async function getJob(id) {
  const response = await api(`/jobs/${encodeURIComponent(id)}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`GET /jobs/${id} failed: ${response.status}`);
  return response.json();
}

// {id, status} when accepted, {error} with the server's error code otherwise.
export async function createJob(text) {
  const response = await api("/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: text }),
  });
  const body = await response.json().catch(() => ({}));
  if (response.ok) return body;
  return { error: body.error || "processing_failed" };
}
