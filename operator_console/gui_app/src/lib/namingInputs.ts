const TOKEN_RE = /^[A-Za-z0-9_]+$/;

export const DEFAULT_OWNER = "LL";
export const DEFAULT_CONTEXT = "General";
export const UNKNOWN_OWNER = "UNKNOWN";
export const UNKNOWN_CONTEXT = "UNKNOWN";
export const DEFAULT_NAMING_STRATEGY = "SHARED_CANONICAL_NAME";

export const NAMING_STRATEGY_OPTIONS = [
  {
    value: DEFAULT_NAMING_STRATEGY,
    label: "Shared canonical name",
    description: "Duplicates share the canonical family name and keep grouping obvious on disk.",
  },
  {
    value: "DUPLICATE_OWNS_DATE_STANDARDIZED",
    label: "Duplicate owns date (standardized)",
    description: "Duplicates still get standardized names, but their own date evidence can drive the date portion.",
  },
  {
    value: "PRESERVE_DUPLICATE_ORIGINAL_NAME",
    label: "Preserve duplicate original name",
    description: "Duplicates keep their original filename while the canonical item stays standardized.",
  },
] as const;

export function formatNamingStrategy(value: string) {
  return NAMING_STRATEGY_OPTIONS.find((option) => option.value === value)?.label ?? value;
}

function validateNamingToken(name: string, value: string, maxLength?: number): string | null {
  if (!value) return `${name} is required`;
  if (value.toUpperCase() === "UNKNOWN") {
    return `${name} must be explicitly classified; UNKNOWN is reserved for ingest-only state`;
  }
  if (maxLength !== undefined && value.length > maxLength) {
    return `${name} must be <= ${maxLength} characters`;
  }
  if (!TOKEN_RE.test(value)) {
    return `${name} must contain only alphanumeric characters or underscore`;
  }
  return null;
}

export function getNamingInputValidation(owner: string, context: string) {
  const ownerError = validateNamingToken("owner", owner);
  const contextError = validateNamingToken("context", context, 20);

  return {
    ownerError,
    contextError,
    isValid: !ownerError && !contextError,
  };
}
