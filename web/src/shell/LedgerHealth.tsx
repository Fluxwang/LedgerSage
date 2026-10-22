import type { LedgerStatus } from "../api";
import { Async, type AsyncState } from "../ui/Async";

export type LedgerHealthState = AsyncState<LedgerStatus>;

export function LedgerHealthChip({ state, onOpen }: { state: LedgerHealthState; onOpen: () => void }) {
  const warning = state.data?.health.find((item) => item.level === "warn");
  const healthy = Boolean(state.data) && !warning && !state.error && !state.loading;
  const committed = state.data?.git.last_commit_at;
  const hours = committed ? Math.max(0, Math.floor((Date.now() - Date.parse(committed)) / 3_600_000)) : 0;
  const text = state.loading
    ? "检查账本…"
    : state.error
      ? "账本健康度读取失败"
      : warning?.text ?? `bean-check ✓ · ${committed ? `${hours} 小时前提交` : "暂无提交"}`;
  return (
    <button className={healthy ? "chip-ok" : "chip-warn"} title={text} onClick={onOpen}>
      <i />
      <span>{text}</span>
    </button>
  );
}

export function LedgerHealthCard({ state }: { state: LedgerHealthState }) {
  return (
    <div className="pcard" id="ledger-health" tabIndex={-1}>
      <header><b>账本健康度</b></header>
      <div className="in">
        <Async state={state}>
          {(status) => status.health.map((item) => (
            <div className="health-row" key={item.key}>
              <span className={item.level === "ok" ? "chip-ok" : "chip-warn"}>
                {item.level === "ok" ? "正常" : "警告"}
              </span>
              <span>{item.text}</span>
            </div>
          ))}
        </Async>
      </div>
    </div>
  );
}
