export const AUTH_TOKEN_KEY = 'token';
export const AUTH_TOKEN_CHANGED_EVENT = 'opencolab-auth-token-changed';

export function getAuthToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
  window.dispatchEvent(new Event(AUTH_TOKEN_CHANGED_EVENT));
}

export function clearAuthToken(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  window.dispatchEvent(new Event(AUTH_TOKEN_CHANGED_EVENT));
}

export function subscribeAuthToken(listener: () => void): () => void {
  const handleStorage = (event: StorageEvent) => {
    if (event.key === AUTH_TOKEN_KEY) {
      listener();
    }
  };
  window.addEventListener(AUTH_TOKEN_CHANGED_EVENT, listener);
  window.addEventListener('storage', handleStorage);
  return () => {
    window.removeEventListener(AUTH_TOKEN_CHANGED_EVENT, listener);
    window.removeEventListener('storage', handleStorage);
  };
}
