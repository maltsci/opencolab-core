import { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import * as authService from '../services/auth';
import { getAuthToken, subscribeAuthToken } from '../services/auth-token';

export function useAuth() {
  const queryClient = useQueryClient();
  const [authToken, setAuthTokenState] = useState(() => getAuthToken());

  useEffect(() => subscribeAuthToken(() => {
    setAuthTokenState(getAuthToken());
  }), []);

  const { data: user, isLoading } = useQuery({
    queryKey: ['auth', 'me', authToken],
    queryFn: authService.getMe,
    retry: false,
    enabled: !!authToken,
  });

  const loginMutation = useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      authService.login(username, password),
    onSuccess: () => {
      setAuthTokenState(getAuthToken());
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
    },
  });

  const logoutMutation = useMutation({
    mutationFn: authService.logout,
    onSuccess: () => {
      setAuthTokenState(null);
      queryClient.clear();
    },
  });

  return {
    user,
    isLoading,
    isAuthenticated: !!user,
    login: loginMutation.mutateAsync,
    logout: logoutMutation.mutateAsync,
    loginError: loginMutation.error,
  };
}
