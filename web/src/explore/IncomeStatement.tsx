import type { Dashboard } from "../api";
import { Bar, monthLabel, num, Stub } from "../ui";
import { SHADES } from "./shades";

export function IncomeStatement({ data }: { data: Dashboard }) {
  const trend = data.monthly_trend.map((point) => ({
    month: point.month,
    amount: Math.abs(Number(point.amount)),
  }));
  const spend = data.categories.reduce(
    (sum, item) => sum + Math.abs(Number(item.amount)),
    0,
  );
  const months = trend.filter((point) => point.amount > 0);
  const average = months.length
    ? trend.reduce((sum, point) => sum + point.amount, 0) / months.length
    : 0;
  const peak = trend.reduce(
    (best, point) => (point.amount > best.amount ? point : best),
    { month: "—", amount: 0 },
  );
  const max = Math.max(1, ...trend.map((point) => point.amount));
  const categoryMax = Math.max(
    1,
    ...data.categories.map((item) => Math.abs(Number(item.amount))),
  );
  return (
    <>
      <div className="kpis">
        <div className="kpi">
          <span>本期支出</span>
          <b>{num(spend, 0)}</b>
          <em>
            {data.period.start} → {data.period.end}
          </em>
        </div>
        <div className="kpi">
          <span>近六月月均支出</span>
          <b>{num(average, 0)}</b>
          <em>{months.length} 个有数据的月份</em>
        </div>
        <div className="kpi">
          <span>最高单月支出</span>
          <b>{num(peak.amount, 0)}</b>
          <em>{peak.month}</em>
        </div>
        <div className="kpi">
          <span>储蓄率</span>
          <b>—</b>
          <em title="待 GET /statements/income">待 GET /statements/income</em>
        </div>
      </div>

      <div className="card">
        <header>
          <h3>月度支出 · 近六月</h3>
          <div className="grow" />
          <div className="linkish">{data.accounts[0]?.currency ?? "CNY"}</div>
        </header>
        <div className="bars">
          {trend.map((point) => (
            <Bar
              key={point.month}
              label={monthLabel(point.month)}
              value={num(point.amount, 0)}
              share={(point.amount / max) * 100}
              peak={point.amount === max && point.amount > 0}
            />
          ))}
        </div>
        <footer>
          <div className="linkish">
            设计稿要的是「按分类堆叠」的月度构成，需要按月 × 分类的聚合
          </div>
        </footer>
      </div>

      <div className="card">
        <header>
          <h3>分类支出 · 本期</h3>
          <div className="grow" />
          <div className="linkish">{data.categories.length} 个分类</div>
        </header>
        <div className={`bars${data.categories.length > 8 ? " scrolly" : ""}`}>
          {data.categories.map((item, index) => {
            const value = Math.abs(Number(item.amount));
            const cut = item.display_name.lastIndexOf(":");
            return (
              <div className="barrow cat" key={item.account}>
                <div className="lbl" title={item.account}>
                  <span className="head">
                    {cut < 0 ? "" : item.display_name.slice(0, cut)}
                  </span>
                  <span className="leaf">
                    {cut < 0 ? item.display_name : item.display_name.slice(cut)}
                  </span>
                </div>
                <div className="track">
                  <i
                    style={{
                      width: `${(value / categoryMax) * 100}%`,
                      background: SHADES[Math.min(index, 3)],
                    }}
                  />
                </div>
                <div className="val">{num(value, 0)}</div>
              </div>
            );
          })}
          {data.categories.length === 0 && (
            <div className="hollow">这个范围内暂无支出</div>
          )}
        </div>
      </div>

      <Stub
        endpoint="GET /statements/income"
        why="设计稿的收支表是「账户层级 × 连续多个月」的矩阵，还带趋势迷你条和下钻。/dashboard 只给单区间的分类合计，拼不出这张表。"
      />
    </>
  );
}
