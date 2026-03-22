import type { ApiEnvelope } from "@/types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api";

export class ApiClientError extends Error {
  constructor(
    message: string,
    public status?: number,
    public errors?: { code?: string; message: string; details?: Record<string, unknown> }[]
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

async function parseEnvelope<T>(response: Response): Promise<ApiEnvelope<T>> {
  if (!response.ok) {
    let msg = `HTTP ${response.status}`;
    let errors: { code?: string; message: string; details?: Record<string, unknown> }[] | undefined;
    try {
      const body = await response.json();
      if (Array.isArray(body?.errors)) {
        errors = body.errors;
      }
      if (errors?.[0]?.message) msg = errors[0].message;
    } catch {}
    throw new ApiClientError(msg, response.status, errors);
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

  // Most canonical /api endpoints wrap payload as { data: { result: ... } }.
  // Status uses { data: ... } directly.
  const maybeWrapped = envelope.data as Record<string, unknown> | null;
  if (maybeWrapped && typeof maybeWrapped === "object" && "result" in maybeWrapped) {
    envelope.data = maybeWrapped.result as T;
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

export async function apiGetJson<T>(
  path: string,
  params?: Record<string, string | number | boolean | undefined>,
  options?: { basePath?: string }
): Promise<T> {
  const basePath = options?.basePath ?? API_BASE;
  const url = new URL(`${basePath}${path}`, window.location.origin);
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
    });
  }
  const res = await fetch(url.toString(), {
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new ApiClientError(`HTTP ${res.status}`, res.status);
  }
  return (await res.json()) as T;
}

export async function apiPost<T>(path: string, body?: unknown): Promise<ApiEnvelope<T>> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  return parseEnvelope<T>(res);
}
