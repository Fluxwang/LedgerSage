import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { auth, clearToken, type Dashboard, dashboard as fetchDashboard, setToken, token, vector as vectorApi } from "./api";
import { Chat } from "./chat/Chat";
import { Explore } from "./explore/Explore";
import { num } from "./ui";
import "./styles.css";

type View = "chat" | "explore";

function Login({ onLogin }: { onLogin: () => void }) {
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

function UserMenu({ username, onExplore, onLogout }: { username: string; onExplore: () => void; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  return (
    <div className="usermenu" ref={box}>
      <button onClick={() => setOpen(!open)}>
        <span className="avatar">{username.slice(0, 1).toUpperCase() || "?"}</span>
        <span style={{ fontSize: 12.5 }}>{username}</span>
        <span style={{ fontSize: 10, color: "var(--ink-3)" }}>{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div className="menu">
          <button disabled title="设置页不在当前范围" style={{ opacity: 0.45, cursor: "not-allowed" }}>
            设置
          </button>
          <button onClick={() => { setOpen(false); onExplore(); }}>统计页面</button>
          <button onClick={onLogout}>退出登录</button>
        </div>
      )}
    </div>
  );
}

function VectorButton() {
  const [state, setState] = useState<any>();
  useEffect(() => {
    vectorApi.status().then(setState).catch(() => {});
  }, []);
  // 全量重建在后台跑，轮询到结束为止，让用户看得到进度。
  useEffect(() => {
    if (state?.status !== "running") return;
    const timer = setInterval(() => vectorApi.status().then(setState).catch(() => {}), 2000);
    return () => clearInterval(timer);
  }, [state?.status]);
  if (!state?.enabled || !(state.empty || state.status === "running" || state.status === "failed")) return null;
  return (
    <button
      className="btn sm"
      disabled={state.status === "running"}
      onClick={async () => {
        setState({ ...state, status: "running", completed: 0, total: 0 });
        await vectorApi.rebuild();
      }}
    >
      {state.status === "running"
        ? `索引中 ${state.completed}/${state.total || "…"}`
        : state.status === "failed"
          ? "索引失败，重试"
          : "建立历史索引"}
    </button>
  );
}

function App() {
  const [authed, setAuthed] = useState(Boolean(token()));
  const [view, setView] = useState<View>("chat");
  const [me, setMe] = useState("");
  const [period, setPeriod] = useState("this_month");
  const [data, setData] = useState<Dashboard>();
  const [seed, setSeed] = useState<{ text: string; nonce: number }>();
  // 账本一变，顶栏笔数、左栏账户树、预算进度都得跟着重算。
  const [revision, setRevision] = useState(0);
  const refresh = () => setRevision((value) => value + 1);

  useEffect(() => {
    if (!authed) return;
    auth.me().then((user) => setMe(user.username)).catch(() => {});
  }, [authed]);

  useEffect(() => {
    if (!authed) return;
    fetchDashboard(period).then(setData).catch(() => setData(undefined));
  }, [authed, period, revision]);

  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  const currency = data?.accounts[0]?.currency ?? "CNY";

  function ask(question: string) {
    setSeed({ text: question, nonce: Date.now() });
    setView("chat");
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <i />
          <b>LedgerSage</b>
        </div>
        <div className="hr" />
        <div className="path">{data ? `${data.period.start} → ${data.period.end}` : "读取账本…"}</div>
        <div className="chip-warn" title="bean-check 与 git 状态需要 GET /ledger/status">
          <i />
          账本状态待接口
        </div>
        <div className="grow" />
        <div className="meta">
          {data ? `${num(data.recent.total)} txns · ${currency}` : "—"}
        </div>
        <VectorButton />
        <button className="btn sm" onClick={() => setView(view === "chat" ? "explore" : "chat")}>
          {view === "chat" ? "📊 打开统计页面" : "← 返回对话"}
        </button>
        <UserMenu
          username={me || "…"}
          onExplore={() => setView("explore")}
          onLogout={() => {
            clearToken();
            setAuthed(false);
          }}
        />
      </header>

      {view === "chat" ? (
        <Chat data={data} seed={seed} onLedgerChanged={refresh} />
      ) : (
        <Explore data={data} period={period} onPeriod={setPeriod} onAsk={ask} onLedgerChanged={refresh} />
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
