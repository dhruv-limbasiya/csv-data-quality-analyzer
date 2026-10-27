import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { authService } from '../services/authService';
import { PUBLIC_DEMO_MODE } from '../config/publicDemo';

const AuthContext = createContext(null);
const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';
const PUBLIC_DEMO_USER = {
  id: 0,
  username: 'Demo Visitor',
  email: 'Synthetic sample data only',
  is_active: true,
};

export function AuthProvider({ children }) {
  const [user, setUser] = useState(PUBLIC_DEMO_MODE ? PUBLIC_DEMO_USER : null);
  const [isLoading, setIsLoading] = useState(true);
  const [authError, setAuthError] = useState(false);

  // Check current session with the backend on app mount
  const checkAuth = useCallback(async () => {
    if (PUBLIC_DEMO_MODE) {
      setUser(PUBLIC_DEMO_USER);
      setAuthError(false);
      setIsLoading(false);
      return;
    }

    try {
      let userData;
      try {
        userData = await authService.getProfile();
      } catch (error) {
        if (!DEMO_MODE || error.response?.status !== 401) {
          throw error;
        }
        userData = await authService.createDemoSession();
      }
      setUser(userData);
      setAuthError(false);
    } catch {
      setUser(null);
      setAuthError(true);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const login = async (credentials) => {
    const userData = await authService.login(credentials);
    setUser(userData);
    setAuthError(false);
    return userData;
  };

  const startDemo = async () => {
    if (!DEMO_MODE) {
      throw new Error('Demo mode is disabled.');
    }

    setIsLoading(true);
    setAuthError(false);
    try {
      const userData = await authService.createDemoSession();
      setUser(userData);
      return userData;
    } catch (error) {
      setAuthError(true);
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  const register = async (data) => {
    const userData = await authService.register(data);
    setUser(userData);
    setAuthError(false);
    return userData;
  };

  const logout = async () => {
    try {
      await authService.logout();
    } finally {
      setUser(null);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        isDemoMode: DEMO_MODE,
        isPublicDemo: PUBLIC_DEMO_MODE,
        authError,
        login,
        startDemo,
        register,
        logout,
        checkAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
