import type { Session, User } from "@supabase/supabase-js";
import { createContext } from "react";

export type AuthSession = Pick<Session, "access_token">;
export type AuthUser = Pick<User, "id" | "email">;

export interface AuthContextValue {
  session: AuthSession | null;
  user: AuthUser | null;
  loading: boolean;
  signInWithEmail: (email: string) => Promise<void>;
  signInWithPassword: (email: string, password: string) => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  signOut: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | undefined>(
  undefined,
);
