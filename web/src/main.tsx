import "./styles/base.css";
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { auth, clearToken, type Dashboard, dashboard as fetchDashboard, token } from "./api";
import { Chat } from "./chat/Chat";
import { Explore } from "./explore/Explore";
import { Login } from "./shell/Login";
import { UserMenu } from "./shell/UserMenu";
import { VectorButton } from "./shell/VectorButton";
import { num } from "./ui";

type View = "chat" | "explore";

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
