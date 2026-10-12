import type { Dashboard } from "../api";
import { num, Stub } from "../ui";
import { SHADES } from "./shades";

export function BalanceSheet({ data }: { data: Dashboard }) {
  const assets = data.accounts.filter((card) => card.kind === "asset");
  const liabilities = data.accounts.filter((card) => card.kind === "liability");
  const assetTotal = assets.reduce(
    (sum, card) => sum + Number(card.balance),
    0,
  );
  const liabilityTotal = liabilities.reduce(
    (sum, card) => sum + Number(card.balance),
    0,
  );
  const netWorth = assetTotal + liabilityTotal;
  const trend = data.monthly_trend
    .map((point) => Math.abs(Number(point.amount)))
    .filter(Boolean);
  const monthlyBurn = trend.length
    ? trend.reduce((sum, value) => sum + value, 0) / trend.length
    : 0;
  const currency = data.accounts[0]?.currency ?? "CNY";

  let offset = 0;
  const slices = assets
    .filter((card) => Number(card.balance) > 0)
    .map((card, index) => {
      const share = assetTotal ? (Number(card.balance) / assetTotal) * 100 : 0;
      const slice = {
        card,
        share,
        from: offset,
        to: offset + share,
        color: SHADES[Math.min(index, 3)],
      };
      offset += share;
      return slice;
    });
  const ring = `conic-gradient(${slices
    .map((slice) => `${slice.color} ${slice.from}% ${slice.to}%`)
    .join(",")}${slices.length ? "" : "var(--wash) 0 100%"})`;

  return (
    <>
      <div className="kpis">
        <div className="kpi">
          <span>净资产</span>
          <b>{num(netWorth, 0)}</b>
          <em>{currency}</em>
        </div>
        <div className="kpi">
          <span>资产</span>
          <b>{num(assetTotal, 0)}</b>
          <em>{assets.length} 个账户</em>
        </div>
        <div className="kpi">
          <span>负债</span>
          <b>{num(liabilityTotal, 0)}</b>
          <em>{liabilities.length} 个账户</em>
        </div>
        <div className="kpi">
          <span>流动性覆盖</span>
          <b>{monthlyBurn ? (netWorth / monthlyBurn).toFixed(1) : "—"} 月</b>
          <em>按近六月月均支出计</em>
        </div>
      </div>

      <div className="card">
        <header>
          <h3>期末余额</h3>
          <div className="grow" />
          <div className="linkish">当前 · 折算为 {currency}</div>
        </header>
        <div
          className={assets.length + liabilities.length > 12 ? "tscroll" : ""}
        >
          <table className="matrix">
            <thead>
              <tr>
                <th>账户</th>
                <th>本期变动</th>
                <th>余额</th>
                <th>占比</th>
              </tr>
            </thead>
            <tbody>
              <tr className="total">
                <td className="lead">Assets</td>
                <td>—</td>
                <td>{num(assetTotal, 2)}</td>
                <td />
              </tr>
              {assets.map((card) => (
                <tr key={card.account}>
                  <td className="lead sub" title={card.account}>
                    {card.display_name}
                  </td>
                  <td>{num(card.change, 2)}</td>
                  <td>{num(card.balance, 2)}</td>
                  <td>
                    <div className="meter">
                      <i
                        style={{
                          width: `${assetTotal ? (Number(card.balance) / assetTotal) * 100 : 0}%`,
                        }}
                      />
                    </div>
                  </td>
                </tr>
              ))}
              <tr className="total">
                <td className="lead">Liabilities</td>
                <td>—</td>
                <td>{num(liabilityTotal, 2)}</td>
                <td />
              </tr>
              {liabilities.map((card) => (
                <tr key={card.account}>
                  <td className="lead sub" title={card.account}>
                    {card.display_name}
                  </td>
                  <td>{num(card.change, 2)}</td>
                  <td>{num(card.balance, 2)}</td>
                  <td>
                    <div className="meter exceeded">
                      <i
                        style={{
                          width: `${liabilityTotal ? (Number(card.balance) / liabilityTotal) * 100 : 0}%`,
                        }}
                      />
                    </div>
                  </td>
                </tr>
              ))}
              <tr className="total">
                <td className="lead">净资产</td>
                <td>—</td>
                <td>{num(netWorth, 2)}</td>
                <td />
              </tr>
            </tbody>
          </table>
        </div>
        <footer>
          <div className="linkish">
            设计稿要的是 07 / 08 / 当前三列期末余额，需要按日期回溯的余额端点
          </div>
        </footer>
      </div>

      <div className="card">
        <header>
          <h3>资产配置</h3>
        </header>
        <div className="body">
          <div className="donut">
            <div
              className="ring"
              style={{
                background: ring,
                mask: "radial-gradient(circle,transparent 52%,#000 53%)",
                WebkitMask: "radial-gradient(circle,transparent 52%,#000 53%)",
              }}
            />
            <div className="pin grow">
              {slices.map((slice) => (
                <div key={slice.card.account}>
                  <span className="n" title={slice.card.account}>
                    <i
                      style={{
                        display: "inline-block",
                        width: 8,
                        height: 8,
                        borderRadius: 2,
                        background: slice.color,
                        marginRight: 7,
                      }}
                    />
                    {slice.card.display_name}
                  </span>
                  <span className="v">{slice.share.toFixed(1)}%</span>
                </div>
              ))}
              {slices.length === 0 && (
                <div className="hollow">还没有资产余额</div>
              )}
            </div>
          </div>
        </div>
      </div>

      <Stub
        endpoint="GET /statements/balance"
        why="净资产走势（近六月）、按月的期末余额列，以及 balance 指令的对账状态，都没有对应端点。"
      />
    </>
  );
}
