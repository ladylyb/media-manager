import type { ApiEnvelope } from "@/types/api";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

export class ApiClientError extends Error {
  constructor(
    message: string,
    public status?: number,
    public errors?: { code?: string; message: string; detail?: string }[]
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

async function parseEnvelope<T>(response: Response): Promise<ApiEnvelope<T>> {
  if (!response.ok) {
    let msg = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (body?.errors?.[0]?.message) msg = body.errors[0].message;
    } catch {}
    throw new ApiClientError(msg, response.status);
  }

  const envelope = (await response.json()) as ApiEnvelope<T>;

  if (!envelope.ok) {
    const firstError = envelope.errors?.[0];
    throw new ApiClientError(
      firstError?.message || "Unknown API error",
      response.status,
      envelope.errors
    );
  }

  return envelope;
}

export async function apiGet<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<ApiEnvelope<T>> {
  const url = new URL(`${API_BASE}${path}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
    });
  }
  const res = await fetch(url.toString(), {
    headers: { Accept: "application/json" },
  });
  return parseEnvelope<T>(res);
}

export async function apiPost<T>(path: string, body?: unknown): Promise<ApiEnvelope<T>> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return parseEnvelope<T>(res);
}
