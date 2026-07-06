import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { api, setToken } from "../api/client";
import { useApp } from "../state/app";

export default function Login() {
  const { t } = useApp();
  const nav = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res = await api.post<{ token: string }>("/api/admin/auth/login", {
        username,
        password,
      });
      setToken(res.token);
      nav("/");
    } catch {
      setError(t.badCreds);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <form className="login-card" onSubmit={submit}>
        <b style={{ letterSpacing: "0.06em" }}>ADMIN CABINET</b>
        <span className="caps">VPN SHOP CONSTRUCTOR</span>
        <input
          className="input"
          placeholder={t.username}
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
          autoComplete="username"
        />
        <input
          className="input"
          type="password"
          placeholder={t.password}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
        {error && (
          <span className="caps" style={{ color: "var(--muted)" }}>
            ✕ {error}
          </span>
        )}
        <button className="btn primary" disabled={busy || !username || !password}>
          {t.login}
        </button>
      </form>
    </div>
  );
}
