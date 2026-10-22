import { useState } from "react";
import { accounts as fetchAccounts, type Dashboard } from "../api";
import { abs, Async, Bar, budgetState, BUDGET_LABEL, Meter, monthLabel, num, Stub, useAsync } from "../ui";
import type { WriteReceipt } from "./Results";
import type { LedgerHealthState } from "../shell/LedgerHealth";

type Tab = "ledger" | "accounts" | "charts";

function Diff({ receipt, health }: { receipt: WriteReceipt; health: LedgerHealthState }) {
  const lines = receipt.added_lines ?? receipt.text.split("\n");
  return (
    <div className="pcard">
      <header>
        <b>{receipt.commit ? "已写入的 diff" : "即将写入的 diff"}</b>
        <span className="chip-ok">+{lines.length} 行</span>
        <div className="grow" />
        <small>L{receipt.insert_at_line}</small>
      </header>
      <pre className="diff">
        {lines.map((line, index) => (
          <span className="add" key={index}>
            <span className="ln">{receipt.insert_at_line + index}</span>
            <span className="sign">+ </span>
            {line}
          </span>
        ))}
      </pre>
      <div className="in">
        <div className="kicker">校验</div>
        <div className="checks">
          {receipt.validations?.map((check) => (
            <div key={check.text}>
              <span className={check.level}>{check.level === "ok" ? "✓" : "!"}</span>
              {check.text}
            </div>
          ))}
        </div>
        <BeanCheck health={health} />
      </div>
    </div>
  );
}

/** 账本此刻的 bean-check 结果，复用顶栏已取到的账本健康度；只提示，不拦确认（ADR 0012）。 */
function BeanCheck({ health }: { health: LedgerHealthState }) {
  const check = health.data?.bean_check;
  if (health.loading) return <div className="checks"><div><span>…</span>bean-check 读取中</div></div>;
  if (health.error || !check)
    return <div className="checks"><div><span className="warn">!</span>bean-check 读取失败：{String((health.error as Error | undefined)?.message ?? "无数据")}</div></div>;
  return (
    <div className="checks">
      <div>
        <span className={check.ok ? "ok" : "warn"}>{check.ok ? "✓" : "!"}</span>
        {check.ok ? "bean-check 通过" : check.message}
      </div>
    </div>
  );
}

function Budgets({ rows }: { rows: Dashboard["budgets"] }) {
  if (rows.length === 0) return null;
  return (
    <div className="pcard">
      <header>
        <b>预算进度</b>
        <div className="grow" />
        <small>{rows.length} 条</small>
      </header>
      <div className="in">
        {rows.map((row) => {
          const used = Number(row.used);
          const limit = Number(row.amount);
          const state = budgetState(used, limit);
          return (
            <div key={row.account} style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 11.5 }}>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {row.display_name}
                </span>
                <span className={`num ${state === "ok" ? "" : "muted"}`} style={{ flex: "none" }}>
                  {limit ? Math.round((used / limit) * 100) : 0}%
                </span>
              </div>
              <Meter used={used} limit={limit} />
              <div className="linkish">
                {num(used, 0)} / {num(limit, 0)} {row.currency} · {BUDGET_LABEL[state]}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Accounts() {
  const state = useAsync(() => fetchAccounts(), []);
  return (
    <Async state={state}>
      {(rows) => (
        <div className="pcard">
          <header>
            <b>账户</b>
            <div className="grow" />
            <small>{rows.length} 个</small>
          </header>
          <div className="in" style={{ gap: 5 }}>
            {rows.map((row) => (
              <div key={row.account} style={{ display: "flex", justifyContent: "space-between", gap: 8, font: "10.5px var(--mono)" }}>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.account}</span>
                <span className="muted" style={{ flex: "none" }}>{row.display_name ?? ""}</span>
              </div>
            ))}
            {rows.length === 0 && <div className="hollow">账本里还没有账户</div>}
          </div>
        </div>
      )}
    </Async>
  );
}

function Charts({ data }: { data: Dashboard }) {
  const trendMax = Math.max(1, ...data.monthly_trend.map((point) => Math.abs(Number(point.amount))));
  const categoryMax = Math.max(1, ...data.categories.map((item) => Math.abs(Number(item.amount))));
  return (
    <>
      <div className="pcard">
        <header>
          <b>近六个月支出</b>
          <div className="grow" />
          <small>{data.accounts[0]?.currency ?? "CNY"}</small>
        </header>
        <div className="bars" style={{ padding: "10px 12px" }}>
          {data.monthly_trend.map((point) => {
            const value = Math.abs(Number(point.amount));
            return (
              <Bar
                key={point.month}
                label={monthLabel(point.month)}
                value={num(value, 0)}
                share={(value / trendMax) * 100}
                peak={value === trendMax && value > 0}
              />
            );
          })}
        </div>
      </div>
      <div className="pcard">
        <header>
          <b>分类支出</b>
          <div className="grow" />
          <small>{data.period.start} → {data.period.end}</small>
        </header>
        <div className="bars" style={{ padding: "10px 12px" }}>
          {data.categories.slice(0, 8).map((item) => {
            const value = Math.abs(Number(item.amount));
            return (
              <Bar
                key={item.account}
                label={item.display_name.slice(0, 5)}
                value={num(value, 0)}
                share={(value / categoryMax) * 100}
              />
            );
          })}
          {data.categories.length === 0 && <div className="hollow">这个范围内暂无支出</div>}
        </div>
      </div>
    </>
  );
}

export function LedgerPanel({
  receipt,
  data,
  health,
  file,
}: {
  receipt?: WriteReceipt;
  data?: Dashboard;
  health: LedgerHealthState;
  file: string;
}) {
  const [tab, setTab] = useState<Tab>("ledger");
  return (
    <aside className="panel">
      <nav>
        {(
          [
            ["ledger", "Ledger"],
            ["accounts", "Accounts"],
            ["charts", "Charts"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button key={key} className={tab === key ? "on" : ""} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
        <div className="file">{file}</div>
      </nav>
      <div className="scroll">
        {tab === "ledger" && (
          <>
            {receipt ? (
              <Diff receipt={receipt} health={health} />
            ) : (
              <div className="hollow">这一栏常驻账本原文。记一笔之后，这里会先显示将要写进去的那几行。</div>
            )}
            {data && <Budgets rows={data.budgets} />}
            <Stub endpoint="GET /ledger/raw" why="写入位置上下文与「查询命中的原始条目」需要按行读取账本原文。" />
            <Stub endpoint="GET /ledger/history" why="右栏「写入历史」要列出最近几次提交与是否已回滚。" />
          </>
        )}
        {tab === "accounts" && <Accounts />}
        {tab === "charts" &&
          (data ? <Charts data={data} /> : <div className="loading">读取账本…</div>)}
      </div>
    </aside>
  );
}

export const totalOf = (rows: { balance: string }[]) =>
  abs(rows.reduce((sum, row) => sum + Number(row.balance), 0), 0);