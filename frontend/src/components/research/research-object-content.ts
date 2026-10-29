export interface StructuredResearchContent {
  overview: string;
  keyPoints: string[];
  contradictions: string[];
  gaps: string[];
  actionItems: string[];
  responseOutline: string[];
  validationNotes: string[];
}

function looksLikeJsonText(value: string): boolean {
  const trimmed = value.trim();
  return (
    (trimmed.startsWith('{') && trimmed.endsWith('}'))
    || (trimmed.startsWith('[') && trimmed.endsWith(']'))
  );
}

function parseJsonObjectFromText(value: string): Record<string, unknown> | null {
  const trimmed = value.trim();
  if (!looksLikeJsonText(trimmed)) {
    return null;
  }

  try {
    const parsed = JSON.parse(trimmed);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : null;
  } catch {
    return null;
  }
}

function toTrimmedString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];

  return value
    .map((item) => {
      if (typeof item === 'string') return item.trim();
      if (item === null || item === undefined) return '';
      return String(item).trim();
    })
    .filter(Boolean);
}

function readValidationNotes(value: unknown): string[] {
  if (!value || typeof value !== 'object') {
    return [];
  }

  return toStringArray((value as { notes?: unknown }).notes);
}

export function normalizeStructuredResearchContent(content: string | null): StructuredResearchContent | null {
  const raw = content?.trim() || '';
  if (!raw) return null;

  const parsed = parseJsonObjectFromText(raw);
  if (!parsed) return null;

  const overview = toTrimmedString(parsed.overview || parsed.summary);
  const keyPoints = toStringArray(parsed.key_points);
  const contradictions = toStringArray(parsed.contradictions);
  const gaps = toStringArray(parsed.gaps);
  const actionItems = toStringArray(parsed.action_items);
  const responseOutline = toStringArray(parsed.response_outline);
  const validationNotes = readValidationNotes(parsed.validation);

  const hasStructuredContent = Boolean(
    overview
    || keyPoints.length
    || contradictions.length
    || gaps.length
    || actionItems.length
    || responseOutline.length
    || validationNotes.length,
  );

  if (!hasStructuredContent) {
    return null;
  }

  return {
    overview,
    keyPoints,
    contradictions,
    gaps,
    actionItems,
    responseOutline,
    validationNotes,
  };
}

export function getStructuredResearchPreview(content: string | null): string {
  const structured = normalizeStructuredResearchContent(content);
  if (!structured) {
    return content?.trim() || '';
  }

  return (
    structured.overview
    || structured.keyPoints[0]
    || structured.actionItems[0]
    || structured.responseOutline[0]
    || structured.contradictions[0]
    || structured.gaps[0]
    || structured.validationNotes[0]
    || ''
  );
}
