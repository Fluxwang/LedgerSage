import "./styles/base.css";
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { auth, clearToken, type Dashboard, dashboard as fetchDashboard, ledgerStatus, token } from "./api";
import { Chat } from "./chat/Chat";
import { Explore } from "./explore/Explore";
import { Login } from "./shell/Login";
import { UserMenu } from "./shell/UserMenu";
import { VectorButton } from "./shell/VectorButton";
import { LedgerHealthChip } from "./shell/LedgerHealth";
import { num, useAsync } from "./ui";
import { RunHistory } from "./history/RunHistory";

type View = "chat" | "explore" | "history";

function App() {
  const [authed, setAuthed] = useState(Boolean(token()));
  const [view, setView] = useState<View>("chat");
  const [me, setMe] = useState("");
  const [period, setPeriod] = useState("this_month");
  const [data, setData] = useState<Dashboard>();
  const [seed, setSeed] = useState<{ text: string; nonce: number; autoSend?: boolean }>();
  // 账本一变，顶栏笔数、左栏账户树、预算进度都得跟着重算。
  const [revision, setRevision] = useState(0);
  const [healthFocus, setHealthFocus] = useState(0);
  const refresh = () => setRevision((value) => value + 1);
  const health = useAsync(() => authed ? ledgerStatus() : Promise.resolve(undefined), [authed, revision]);

  useEffect(() => {
    if (!authed) return;
    auth.me().then((user) => setMe(user.username)).catch(() => {});
  }, [authed]);

  useEffect(() => {
    if (!authed) return;
    let live = true;
    fetchDashboard(period).then((result) => live && setData(result)).catch(() => live && setData(undefined));
    return () => { live = false; };
  }, [authed, period, revision]);

  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  const currency = data?.accounts[0]?.currency ?? "CNY";

  function ask(question: string, autoSend = false) {
    setSeed({ text: question, nonce: Date.now(), autoSend });
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
        <LedgerHealthChip state={health} onOpen={() => {
          setView("explore");
          setHealthFocus((value) => value + 1);
        }} />
        <div className="grow" />
        <div className="meta">
          {data ? `${num(data.recent.total)} txns · ${currency}` : "—"}
        </div>
        <VectorButton />
        <button className="btn sm" onClick={() => setView(view === "history" ? "chat" : "history")}>
          {view === "history" ? "← 返回对话" : "决策历史"}
        </button>
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
        <Chat data={data} health={health} seed={seed} onSeedConsumed={() => setSeed(undefined)} onLedgerChanged={refresh} />
      ) : view === "history" ? (
        <RunHistory />
      ) : (
        <Explore data={data} health={health} healthFocus={healthFocus} period={period} onPeriod={setPeriod} onAsk={ask} onSavedAsk={(question) => ask(question, true)} onLedgerChanged={refresh} />
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
