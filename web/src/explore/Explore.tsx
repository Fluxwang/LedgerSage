import "./explore.css";
import { useEffect, useState } from "react";
import type { Dashboard } from "../api";
import type { LedgerHealthState } from "../shell/LedgerHealth";
import { Picker } from "../ui";
import { BalanceSheet } from "./BalanceSheet";
import { IncomeStatement } from "./IncomeStatement";
import { SideRail } from "./SideRail";
import { Transactions } from "./Transactions";
import { Tree } from "./Tree";

type Tab = "is" | "bs" | "tx";

const PERIODS: [string, string][] = [
  ["this_week", "本周"],
  ["this_month", "本月"],
  ["this_year", "今年"],
];

export function Explore({
  data,
  health,
  healthFocus,
  period,
  onPeriod,
  onAsk,
  onSavedAsk,
  onLedgerChanged,
}: {
  data?: Dashboard;
  health: LedgerHealthState;
  healthFocus: number;
  period: string;
  onPeriod: (period: string) => void;
  onAsk: (question: string) => void;
  onSavedAsk: (question: string) => void;
  onLedgerChanged: () => void;
}) {
  const [tab, setTab] = useState<Tab>("is");
  const [account, setAccount] = useState("");
  const [text, setText] = useState("");
  useEffect(() => {
    if (!healthFocus) return;
    const card = document.getElementById("ledger-health");
    card?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    card?.focus({ preventScroll: true });
  }, [healthFocus]);

  return (
    <div className="explore">
      <nav className="subnav">
        {(
          [
            ["is", "收支表"],
            ["bs", "资产负债"],
            ["tx", "流水"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            className={`tab${tab === key ? " on" : ""}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
        <div className="off" title="多币种与投资持仓不在当前范围">
          持仓
        </div>
        <div
          className="off"
          title="ADR 0006：不让 LLM 生成 BQL，也没有暴露 BQL 端点"
        >
          BQL 查询
        </div>
        <div className="grow" />
        <button className="btn sm" onClick={() => onAsk("帮我看看这张表")}>
          在对话里追问这张表
        </button>
      </nav>

      <div className="filters">
        <div className="field">
          <span>时间</span>
          <Picker
            bare
            label="时间范围"
            value={period}
            onChange={onPeriod}
            options={PERIODS.map(([key, label]) => ({ value: key, label }))}
          />
        </div>
        <div className="field">
          <span>账户</span>
          <input
            value={account}
            onChange={(event) => setAccount(event.target.value)}
            placeholder="Expenses:"
          />
        </div>
        <div className="field">
          <span>筛选</span>
          <input
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder="收款方 / 摘要"
          />
        </div>
        <div className="hint">
          {data
            ? `${data.period.start} → ${data.period.end} · 共 ${data.recent.total} 笔`
            : "读取中…"}
        </div>
      </div>

      <div className="explore-body">
        <aside className="rail">
          <div className="rail-group">
            <div className="kicker">账户树</div>
            {data && (
              <Tree
                data={data}
                onPick={(prefix) => setAccount(prefix === account ? "" : prefix)}
                picked={account}
              />
            )}
          </div>
          <div className="grow" />
        </aside>
        <main className="explore-main">
          {!data && <div className="loading">账本暂不可用，请查看右栏健康度</div>}
          {data && tab === "is" && <IncomeStatement data={data} />}
          {data && tab === "bs" && <BalanceSheet data={data} />}
          {data && tab === "tx" && (
            <Transactions
              period={data.period}
              filter={{ account, text }}
              budgets={data.budgets}
              onLedgerChanged={onLedgerChanged}
            />
          )}
        </main>
        <SideRail data={data} health={health} onAsk={onAsk} onSavedAsk={onSavedAsk} />
      </div>
    </div>
  );
}
