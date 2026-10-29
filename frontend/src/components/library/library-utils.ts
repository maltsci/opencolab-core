/**
 * Format an ISO date string for display, using the active i18n language.
 * Returns '-' for missing or invalid values.
 */
export function formatDateTime(value: string | null | undefined, language: string): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString(language.startsWith('zh') ? 'zh-CN' : 'en-US', { hour12: false });
}
