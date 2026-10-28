import "./explore.css";
import { useEffect, useState } from "react";
import type { Dashboard } from "../api";
import type { LedgerHealthState } from "../shell/LedgerHealth";
import { Picker } from "../ui";
import { BalanceSheet } from "./BalanceSheet";
import { type Drill, IncomeStatement, RANGES } from "./IncomeStatement";
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
  const [months, setMonths] = useState("6");
  /** 从收支表格子下钻时流水页用这个范围；改顶部时间范围就回到常规行为。 */
  const [drill, setDrill] = useState<Drill | null>(null);
  /** 退出下钻：日期回到顶部区间，下钻带进来的账户前缀一并清掉。 */
  const leaveDrill = () => {
    if (drill) setAccount("");
    setDrill(null);
  };
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
        <div className="grow" />
        <button className="btn sm" onClick={() => onAsk("帮我看看这张表")}>
          在对话里追问这张表
        </button>
      </nav>

      <div className="filters">
        <div className="field">
          <span>时间</span>
          {tab === "is" ? (
            <Picker
              bare
              label="收支表月份范围"
              value={months}
              onChange={setMonths}
              options={RANGES.map(([key, label]) => ({ value: key, label }))}
            />
          ) : (
            <Picker
              bare
              label="时间范围"
              value={period}
              onChange={(value) => {
                leaveDrill();
                onPeriod(value);
              }}
              options={PERIODS.map(([key, label]) => ({ value: key, label }))}
            />
          )}
        </div>
        {tab !== "is" && (
          <>
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
          </>
        )}
        <div className="hint">
          {drill && tab === "tx" ? (
            <>
              下钻 {drill.start} → {drill.end}{" "}
              <button className="linkish" onClick={leaveDrill}>
                回到{PERIODS.find(([key]) => key === period)?.[1] ?? "本月"}
              </button>
            </>
          ) : tab === "is" ? (
            `收支表 · ${RANGES.find(([key]) => key === months)?.[1]} · 点格子看流水`
          ) : data ? (
            `${data.period.start} → ${data.period.end} · 共 ${data.recent.total} 笔`
          ) : (
            "读取中…"
          )}
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
          {data && tab === "is" && (
            <IncomeStatement
              months={months}
              refreshKey={data}
              onDrill={(next) => {
                setDrill(next);
                setAccount(next.account);
                setTab("tx");
              }}
            />
          )}
          {data && tab === "bs" && <BalanceSheet data={data} />}
          {data && tab === "tx" && (
            <Transactions
              period={drill ?? data.period}
              filter={{ account, text }}
              budgets={data.budgets}
              onLedgerChanged={onLedgerChanged}
            />
          )}
        </main>
        <SideRail
          data={data}
          health={health}
          onAsk={onAsk}
          onSavedAsk={onSavedAsk}
        />
      </div>
    </div>
  );
}
