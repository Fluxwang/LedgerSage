import { type Dashboard, savedQueries } from "../api";
import { LedgerHealthCard, type LedgerHealthState } from "../shell/LedgerHealth";
import { useState } from "react";
import {
  Async,
  budgetState,
  BUDGET_LABEL,
  Meter,
  num,
  useAsync,
} from "../ui";

export function SideRail({
  data,
  health,
  onAsk,
  onSavedAsk,
}: {
  data?: Dashboard;
  health: LedgerHealthState;
  onAsk: (question: string) => void;
  onSavedAsk: (question: string) => void;
}) {
  const saved = useAsync(() => savedQueries.list(), []);
  const [deleting, setDeleting] = useState<string>();
  const [deleteError, setDeleteError] = useState("");
  async function remove(id: string) {
    setDeleting(id);
    setDeleteError("");
    try {
      await savedQueries.remove(id);
      saved.reload();
    } catch (reason) {
      setDeleteError((reason as Error).message);
    } finally {
      setDeleting(undefined);
    }
  }
  return (
    <aside className="panel">
      <div className="scroll">
        <div className="pcard">
          <header>
            <b>前十收款方</b>
          </header>
          <div className="in panel-list payee-list" role="region" aria-label="前十收款方列表" tabIndex={0}>
            <div className="pin">
              {data?.top_payees.map((row) => (
                <div key={row.payee}>
                  <span className="n">{row.payee}</span>
                  <span className="v">{num(row.amount, 0)}</span>
                </div>
              ))}
            </div>
            {!data && <div className="hollow">暂时无法读取排行</div>}
            {data?.top_payees.length === 0 && <div className="hollow">当前区间没有收款方支出</div>}
          </div>
        </div>

        <div className="pcard">
          <header>
            <b>预算进度 · 本月</b>
          </header>
          <div className="in panel-list" role="region" aria-label="预算进度列表" tabIndex={0}>
            {data?.budgets.map((row) => {
              const used = Number(row.used);
              const limit = Number(row.amount);
              const state = budgetState(used, limit);
              return (
                <div
                  key={row.account}
                  style={{ display: "flex", flexDirection: "column", gap: 5 }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      fontSize: 11.5,
                    }}
                  >
                    <span>{row.display_name}</span>
                    <span className="num">
                      {limit ? Math.round((used / limit) * 100) : 0}%
                    </span>
                  </div>
                  <Meter used={used} limit={limit} />
                  <div className="linkish">
                    {BUDGET_LABEL[state]} · 剩余 {num(row.remaining, 0)}
                  </div>
                </div>
              );
            })}
            {data?.budgets.length === 0 && (
              <div className="hollow">还没有设置预算</div>
            )}
          </div>
        </div>

        <LedgerHealthCard state={health} />

        <div className="pcard">
          <header>
            <b>常用查询</b>
          </header>
          <div className="in panel-list" role="region" aria-label="常用查询列表" tabIndex={0}>
            <Async state={saved}>
              {(rows) => (
                <>
                  {rows.map((row) => (
                    <div className="saved-query" key={row.id}>
                      <button className="btn sm saved-question" onClick={() => onSavedAsk(row.question)}>
                        {row.question}
                      </button>
                      <button className="saved-delete btn sm" aria-label={`删除常用查询：${row.question}`}
                        disabled={!!deleting} onClick={() => remove(row.id)}>×</button>
                    </div>
                  ))}
                  {rows.length === 0 && <div className="hollow">在对话的查询结果上点「☆ 存为常用」即可收藏。</div>}
                </>
              )}
            </Async>
            {deleteError && <div className="failed" role="alert">{deleteError}</div>}
          </div>
        </div>

        <div className="pcard">
          <header>
            <b>把这张视图交给 Agent</b>
          </header>
          <div className="in">
            <button
              className="btn sm"
              onClick={() => onAsk("为什么这个月餐饮涨这么多？")}
            >
              为什么这个月餐饮涨这么多？
            </button>
            <button
              className="btn sm"
              onClick={() => onAsk("剔除聚餐后重算这个月的支出")}
            >
              剔除聚餐后重算这个月的支出
            </button>
            <div className="linkish" style={{ lineHeight: 1.6 }}>
              当前筛选条件还没有带进对话，需要 /chat/stream 接受 context 参数。
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
