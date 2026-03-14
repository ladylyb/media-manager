import type { ApiEnvelope } from "@/types/api";

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

export async function parseEnvelope<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let msg = `HTTP ${response.status}`;
    try {
      const body = await response.json();
      if (body?.errors?.[0]?.message) msg = body.errors[0].message;
    } catch {
      // ignore parse errors
    }
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

  return envelope.data;
}
