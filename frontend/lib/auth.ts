export type AuthUser = {
  token: string;
  user_id: string;
  email: string;
  role: string;
};

export function saveAuth(user: AuthUser): void {
  localStorage.setItem("token", user.token);
  localStorage.setItem("user", JSON.stringify(user));
}

export function getAuth(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("user");
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function clearAuth(): void {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
}

export function isAdmin(): boolean {
  return getAuth()?.role === "admin";
}
