import "../styles/login.css";
import React, { useState } from "react";
import { auth, setToken } from "../api";

export function Login({ onLogin }: { onLogin: () => void }) {
  const [register, setRegister] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);
    const form = Object.fromEntries(new FormData(event.currentTarget)) as any;
    try {
      const result = register ? await auth.register(form) : await auth.login(form);
      setToken(result.access_token);
      onLogin();
    } catch (reason) {
      setError(String((reason as Error).message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <form onSubmit={submit}>
        <div className="mark" />
        <h1>LedgerSage</h1>
        <div className="tag">让每一笔，都有清楚的来处。</div>
        <label>
          用户名
          <input name="username" autoComplete="username" required />
        </label>
        <label>
          密码
          <input name="password" type="password" minLength={8} required />
        </label>
        {register && (
          <label>
            邀请码
            <input name="invite_code" required />
          </label>
        )}
        <button className="btn primary" disabled={busy}>
          {register ? "创建账户" : "登录"}
        </button>
        {error && <div className="err">{error}</div>}
        <button type="button" className="btn ghost" style={{ width: "100%", justifyContent: "center", marginTop: 12 }} onClick={() => setRegister(!register)}>
          {register ? "已有账户，去登录" : "使用邀请码注册"}
        </button>
      </form>
    </main>
  );
}
