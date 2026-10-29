import apiClient from './api-client';
import { clearAuthToken, setAuthToken } from './auth-token';

export interface User {
  id: string;
  username: string;
  display_name: string | null;
  role: string;
}

export interface LoginResponse {
  token: string;
  user: User;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>('/auth/login', {
    username,
    password,
  });
  setAuthToken(data.token);
  return data;
}

export async function logout(): Promise<void> {
  await apiClient.post('/auth/logout');
  clearAuthToken();
}

export async function getMe(): Promise<User> {
  const { data } = await apiClient.get<User>('/auth/me');
  return data;
}
