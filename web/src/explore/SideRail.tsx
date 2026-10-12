import { type Dashboard, savedQueries, topPayees } from "../api";
import {
  Async,
  budgetState,
  BUDGET_LABEL,
  Meter,
  num,
  Stub,
  useAsync,
} from "../ui";

export function SideRail({
  data,
  onAsk,
}: {
  data: Dashboard;
  onAsk: (question: string) => void;
}) {
  const payees = useAsync(
    () =>
      topPayees({ start: data.period.start, end: data.period.end, limit: 10 }),
    [data.period.start],
  );
  const saved = useAsync(() => savedQueries.list(), []);
  return (
    <aside className="panel">
      <div className="scroll">
        <div className="pcard">
          <header>
            <b>前十收款方</b>
          </header>
          <div className="in">
            <Async state={payees}>
              {(rows) => (
                <div className="pin">
                  {rows.map((row) => (
                    <div key={row.payee}>
                      <span className="n">{row.payee}</span>
                      <span className="v">{num(row.amount, 0)}</span>
                    </div>
                  ))}
                </div>
              )}
            </Async>
          </div>
        </div>

        <div className="pcard">
          <header>
            <b>预算进度 · 本月</b>
          </header>
          <div className="in">
            {data.budgets.map((row) => {
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
            {data.budgets.length === 0 && (
              <div className="hollow">还没有设置预算</div>
            )}
          </div>
        </div>

        <div className="pcard">
          <header>
            <b>账本健康度</b>
          </header>
          <div className="in">
            <Stub
              endpoint="GET /ledger/status"
              why="bean-check、缺收款方笔数、超期未对账账户、git 同步时间。"
            />
          </div>
        </div>

        <div className="pcard">
          <header>
            <b>常用查询</b>
          </header>
          <div className="in">
            <Async state={saved}>
              {(rows) => (
                <>
                  {rows.map((row) => (
                    <button
                      className="btn sm"
                      key={row.id}
                      onClick={() => onAsk(row.title)}
                    >
                      {row.title}
                    </button>
                  ))}
                </>
              )}
            </Async>
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
