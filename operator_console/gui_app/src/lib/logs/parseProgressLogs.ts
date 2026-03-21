import type { LogPhase, ParsedLogState } from "@/types/logs";

const MESSAGE_PROGRESS_PATTERN =
  /Progress:\s*(\d+)\/(\d+)\s+(?:files|items)\s+\(([\d.]+)%\)\s+\|\s+([\d.]+)\s+(?:files|items)\/sec/i;

function extractNumber(line: string, field: string): number | null {
  const match = line.match(new RegExp(`${field}=([0-9.]+)`));
  if (!match) return null;
  const parsed = Number(match[1]);
  return Number.isFinite(parsed) ? parsed : null;
}

function extractPhase(line: string): LogPhase {
  const match = line.match(/phase=(ingest|plan|apply|canonical|tag_enrichment|tag)\b/);
  const phase = match?.[1];
  if (phase === "tag_enrichment") return "tag";
  return (phase as LogPhase | undefined) ?? null;
}

function extractStage(line: string): string | null {
  const match = line.match(/stage=([A-Za-z0-9_.-]+)/);
  return match?.[1] ?? null;
}

function parseLine(line: string) {
  const processedCount = extractNumber(line, "processed_count");
  const totalCount = extractNumber(line, "total_count");
  const progressPercent = extractNumber(line, "progress_percent");
  const throughputFps = extractNumber(line, "throughput_fps");

  if (
    processedCount !== null &&
    totalCount !== null &&
    progressPercent !== null &&
    throughputFps !== null
  ) {
    return {
      phase: extractPhase(line),
      stage: extractStage(line),
      processedCount,
      totalCount,
      progressPercent,
      throughputFps,
    };
  }

  const messageMatch = line.match(MESSAGE_PROGRESS_PATTERN);
  if (!messageMatch) return null;

  return {
    phase: extractPhase(line),
    stage: extractStage(line),
    processedCount: Number(messageMatch[1]),
    totalCount: Number(messageMatch[2]),
    progressPercent: Number(messageMatch[3]),
    throughputFps: Number(messageMatch[4]),
  };
}

export function mergeLogLines(previousLines: string[], nextLines: string[], limit = 100): string[] {
  if (previousLines.length === 0) {
    return nextLines.slice(-limit);
  }

  const maxOverlap = Math.min(previousLines.length, nextLines.length);
  for (let overlap = maxOverlap; overlap > 0; overlap -= 1) {
    const previousTail = previousLines.slice(-overlap);
    const nextHead = nextLines.slice(0, overlap);
    if (previousTail.every((line, index) => line === nextHead[index])) {
      return [...previousLines, ...nextLines.slice(overlap)].slice(-limit);
    }
  }

  return nextLines.slice(-limit);
}

export function getLogLineTone(line: string): "default" | "warning" | "error" {
  const upper = line.toUpperCase();
  if (upper.includes("ERROR") || upper.includes("FAILED")) {
    return "error";
  }
  if (upper.includes("WARN") || upper.includes("WARNING")) {
    return "warning";
  }
  return "default";
}

export function parseProgressLogs(lines: string[]): ParsedLogState {
  const candidates = lines
    .map((line) => {
      const parsed = parseLine(line);
      if (!parsed) return null;
      return { ...parsed, line };
    })
    .filter((candidate): candidate is NonNullable<typeof candidate> => candidate !== null);

  const latest = [...candidates].reverse().find(Boolean) ?? null;
  const selected = latest;

  if (!selected) {
    return {
      phase: null,
      stage: null,
      processedCount: null,
      totalCount: null,
      progressPercent: null,
      throughputFps: null,
      lines,
      status: "idle",
    };
  }

  return {
    phase: selected.phase,
    stage: selected.stage,
    processedCount: selected.processedCount,
    totalCount: selected.totalCount,
    progressPercent: selected.progressPercent,
    throughputFps: selected.throughputFps,
    lines,
    status: (selected.progressPercent ?? 100) < 100 ? "running" : "idle",
  };
}
