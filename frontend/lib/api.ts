const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export interface CreateVideoRequest {
  idea: string;
  language: string;
  duration: number;
}

export interface ProjectResponse {
  id: string;
  title: string;
  idea: string;
  language: string;
  duration: number;
  status: string;
  credits_used: number;
  created_at: string;
}

export interface StatusResponse {
  id: string;
  status: string;
  stage: string;
  progress: number;
  scenes_completed: number;
  scenes_total: number;
  estimated_time_remaining: number | null;
  download_url: string | null;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  createVideo: (data: CreateVideoRequest) =>
    request<ProjectResponse>("/video/create", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getStatus: (projectId: string) =>
    request<StatusResponse>(`/video/status/${projectId}`),

  getProject: (projectId: string) =>
    request<ProjectResponse>(`/video/project/${projectId}`),

  getDownloadUrl: (projectId: string) =>
    request<{ download_url: string }>(`/video/download/${projectId}`),

  getCredits: () =>
    request<{ credits_remaining: number; plan: string; videos_today: number }>(
      "/video/credits"
    ),
};
