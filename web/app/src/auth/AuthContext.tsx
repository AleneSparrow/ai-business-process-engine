import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, ApiError, type StaffUser } from "../api/client";

const TOKEN_STORAGE_KEY = "atelier.session_token";

interface AuthContextValue {
  user: StaffUser | null;
  token: string | null;
  loading: boolean;
  signup: (email: string, password: string) => Promise<StaffUser>;
  login: (email: string, password: string) => Promise<StaffUser>;
  logout: () => Promise<void>;
  setUser: (user: StaffUser) => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_STORAGE_KEY));
  const [user, setUserState] = useState<StaffUser | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const setUser = useCallback((nextUser: StaffUser) => setUserState(nextUser), []);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      if (!token) {
        setLoading(false);
        return;
      }
      try {
        const me = await api.me(token);
        if (!cancelled) setUserState(me);
      } catch {
        if (!cancelled) {
          setToken(null);
          localStorage.removeItem(TOKEN_STORAGE_KEY);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    bootstrap();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const signup = useCallback(async (email: string, password: string) => {
    const session = await api.signup(email, password);
    localStorage.setItem(TOKEN_STORAGE_KEY, session.token);
    setToken(session.token);
    setUserState(session.user);
    return session.user;
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const session = await api.login(email, password);
    localStorage.setItem(TOKEN_STORAGE_KEY, session.token);
    setToken(session.token);
    setUserState(session.user);
    return session.user;
  }, []);

  const logout = useCallback(async () => {
    if (token) {
      try {
        await api.logout(token);
      } catch {
        // Best effort — clear local state regardless of whether the server call succeeded.
      }
    }
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    setToken(null);
    setUserState(null);
  }, [token]);

  return (
    <AuthContext.Provider value={{ user, token, loading, signup, login, logout, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}

/** Turns an ApiError's backend error code into copy a business owner can act on. */
export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.code) {
      case "email_already_registered":
        return "An account with this email already exists — try logging in instead.";
      case "invalid_credentials":
        return "That email or password isn't right.";
      case "account_already_has_business":
        return "This account already has a business set up.";
      case "business_id_taken":
        return "That business name is already taken — try a slightly different name.";
      case "validation_error":
        return "Please check the highlighted fields and try again.";
      case "network_error":
        return err.message;
      default:
        return err.message || "Something went wrong. Please try again.";
    }
  }
  return "Something went wrong. Please try again.";
}
