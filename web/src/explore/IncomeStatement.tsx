import { incomeStatement, type IncomeRow, type IncomeStatement as Statement } from "../api";
import { Async, monthLabel, monthsBack, num, useAsync } from "../ui";
import { SHADES } from "./shades";

/** 收支表自己的月份范围，不跟随顶部的本周 / 本月 / 今年。 */
export const RANGES: [string, string][] = [
  ["3", "近 3 个月"],
  ["6", "近 6 个月"],
  ["12", "近 12 个月"],
  ["24", "近 24 个月"],
];

/** 下钻到流水用的闭区间：该账户前缀 + 那个月的起止日期。 */
export type Drill = { account: string; start: string; end: string };

const total = (row?: IncomeRow) => (row ? row.cells.reduce((sum, cell) => sum + Number(cell), 0) : 0);

/** 当月截到 through，其余月份到月末。 */
function monthEnd(period: Statement["periods"][number]) {
  if (period.through) return period.through;
  const [year, month] = period.period.split("-").map(Number);
  return `${period.period}-${String(new Date(year, month, 0).getDate()).padStart(2, "0")}`;
}

export function IncomeStatement({
  months,
  refreshKey,
  onDrill,
}: {
  months: string;
  /** 账本变动后仪表盘会重新拉取，借它的引用变化触发收支表重载。 */
  refreshKey: unknown;
  onDrill: (drill: Drill) => void;
}) {
  const state = useAsync(() => incomeStatement({ start: monthsBack(Number(months)) }), [months, refreshKey]);
  return <Async state={state}>{(data) => <Report data={data} onDrill={onDrill} />}</Async>;
}

function Report({ data, onDrill }: { data: Statement; onDrill: (drill: Drill) => void }) {
  const income = data.rows.find((row) => row.account === "Income");
  const expense = data.rows.find((row) => row.account === "Expenses");
  const totalIncome = total(income);
  const totalExpense = total(expense);
  const net = totalIncome - totalExpense;
  const peakIndex = (expense?.cells ?? []).reduce(
    (best, cell, index, cells) => (Number(cell) > Number(cells[best]) ? index : best),
    0,
  );
  const peak = data.periods[peakIndex];
  const range = data.periods.length
    ? `${data.periods[0].period} → ${data.periods[data.periods.length - 1].period}`
    : "";

  return (
    <>
      <div className="kpis">
        <div className="kpi">
          <span>总收入</span>
          <b>{num(totalIncome, 0)}</b>
          <em>{range}</em>
        </div>
        <div className="kpi">
          <span>总支出</span>
          <b>{num(totalExpense, 0)}</b>
          <em>
            峰值 {peak && Number(expense?.cells[peakIndex]) > 0 ? `${monthLabel(peak.period)} ${num(expense!.cells[peakIndex], 0)}` : "—"}
          </em>
        </div>
        <div className="kpi">
          <span>结余</span>
          <b>{num(net, 0)}</b>
          <em className={net < 0 ? "up" : "down"}>{net < 0 ? "花超了" : "有结余"}</em>
        </div>
        <div className="kpi">
          <span>储蓄率</span>
          {/* 按整段合计再算；没有收入时没有定义（CONTEXT.md） */}
          <b>{totalIncome ? `${((net / totalIncome) * 100).toFixed(1)}%` : "—"}</b>
          <em>{totalIncome ? "（收入 − 支出）/ 收入" : "这段时间没有收入"}</em>
        </div>
      </div>

      <Composition data={data} />

      <div className="card">
        <header>
          <h3>收支表 · 按月</h3>
          <div className="grow" />
          <div className="linkish">{data.currency}</div>
        </header>
        <div className={data.rows.length > 12 ? "tscroll" : ""}>
          <table className="matrix">
            <thead>
              <tr>
                <th>账户</th>
                <th>趋势</th>
                {data.periods.map((period) => (
                  <th key={period.period} title={period.through ? `截至 ${period.through}` : undefined}>
                    {monthLabel(period.period)}
                    {period.partial && period.through && <small> · 截至 {period.through.slice(5)}</small>}
                  </th>
                ))}
                <th>合计</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((row) => (
                <tr key={row.account} className={row.depth === 0 ? "total" : ""}>
                  <td className="lead" title={row.account} style={{ paddingLeft: 15 + row.depth * 14 }}>
                    {row.display_name}
                  </td>
                  <td>
                    <Spark cells={row.cells} />
                  </td>
                  {row.cells.map((cell, index) => (
                    <td key={data.periods[index].period}>
                      <button
                        className="cellbtn"
                        title={`查看 ${row.display_name} ${data.periods[index].period} 的流水`}
                        onClick={() =>
                          onDrill({
                            account: row.account,
                            start: `${data.periods[index].period}-01`,
                            end: monthEnd(data.periods[index]),
                          })
                        }
                      >
                        {Number(cell) ? num(cell, 0) : "·"}
                      </button>
                    </td>
                  ))}
                  <td>{num(total(row), 0)}</td>
                </tr>
              ))}
              <tr className="total">
                <td className="lead">结余</td>
                <td />
                {data.periods.map((period, index) => (
                  <td key={period.period}>
                    {num(Number(income?.cells[index] ?? 0) - Number(expense?.cells[index] ?? 0), 0)}
                  </td>
                ))}
                <td>{num(net, 0)}</td>
              </tr>
            </tbody>
          </table>
        </div>
        {data.skipped_currencies.length > 0 && (
          <footer>
            <div className="linkish">
              有外币交易未计入（{data.skipped_currencies.join("、")}），表中只统计 {data.currency}
            </div>
          </footer>
        )}
      </div>
    </>
  );
}

function Spark({ cells }: { cells: string[] }) {
  const max = Math.max(1, ...cells.map((cell) => Math.abs(Number(cell))));
  return (
    <div className="spark">
      {cells.map((cell, index) => (
        <i key={index} style={{ height: `${Math.max(1, (Math.abs(Number(cell)) / max) * 16)}px` }} />
      ))}
    </div>
  );
}

/** 每月支出按第一层分类堆叠；超过三类的部分并为「其他」。 */
function Composition({ data }: { data: Statement }) {
  const groups = data.rows.filter((row) => row.depth === 1 && row.account.startsWith("Expenses:"));
  const parts = groups.slice(0, 3).map((row) => ({ label: row.display_name, cells: row.cells.map(Number) }));
  if (groups.length > 3)
    parts.push({
      label: "其他",
      cells: data.periods.map((_, index) =>
        groups.slice(3).reduce((sum, row) => sum + Number(row.cells[index]), 0),
      ),
    });
  const heights = data.periods.map((_, index) =>
    parts.reduce((sum, part) => sum + Math.max(0, part.cells[index]), 0),
  );
  const max = Math.max(1, ...heights);
  return (
    <div className="card">
      <header>
        <h3>月度支出构成</h3>
        <div className="grow" />
        <div className="legend">
          {parts.map((part, index) => (
            <div key={part.label}>
              <i style={{ background: SHADES[index] }} />
              {part.label}
            </div>
          ))}
        </div>
      </header>
      {parts.length === 0 ? (
        <div className="hollow">这个范围内暂无支出</div>
      ) : (
        <>
          <div className="stack">
            {data.periods.map((period, index) => (
              <div className="stackcol" key={period.period} title={`${period.period} · ${num(heights[index], 0)}`}>
                {/* 自上而下画，最大的分类落在柱底 */}
                {[...parts].reverse().map((part) => (
                  <i
                    key={part.label}
                    style={{
                      height: `${(Math.max(0, part.cells[index]) / max) * 168}px`,
                      background: SHADES[parts.indexOf(part)],
                    }}
                  />
                ))}
              </div>
            ))}
          </div>
          <div className="axis">
            {data.periods.map((period) => (
              <div key={period.period}>
                {monthLabel(period.period)}
                {period.partial ? "*" : ""}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
