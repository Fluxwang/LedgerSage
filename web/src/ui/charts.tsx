export function Bar({ label, value, share, peak }: { label: string; value: string; share: number; peak?: boolean }) {
  return (
    <div className={`barrow${peak ? " peak" : ""}`}>
      <div className="lbl">{label}</div>
      <div className="track">
        <i style={{ width: `${Math.max(0, Math.min(100, share))}%` }} />
      </div>
      <div className="val">{value}</div>
    </div>
  );
}

export function Meter({ used, limit }: { used: number; limit: number }) {
  const ratio = limit ? used / limit : 0;
  const state = ratio >= 1 ? "exceeded" : ratio >= 0.75 ? "at-risk" : "ok";
  return (
    <div className={`meter ${state}`}>
      <i style={{ width: `${Math.min(100, ratio * 100)}%` }} />
    </div>
  );
}

export const budgetState = (used: number, limit: number) =>
  limit && used >= limit ? "exceeded" : limit && used / limit >= 0.75 ? "at-risk" : "ok";

export const BUDGET_LABEL: Record<string, string> = { exceeded: "已超支", "at-risk": "即将超支", ok: "健康" };
