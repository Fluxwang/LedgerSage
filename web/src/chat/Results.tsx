import { useState } from "react";
import { confirmWrite, editWrite, rejectWrite, undoCommit, type Validation } from "../api";
import { abs, Bar, budgetState, BUDGET_LABEL, Disclose, Meter, num, Picker } from "../ui";

/* tools 节点的回执。带 pending_id 的是预览，带 commit 的是已落盘（ADR 0012）。 */
export type WriteReceipt = {
  kind: "write";
  file: string;
  insert_at_line: number;
  entries: string[];
  text: string;
  added_lines: string[];
  balanced: boolean;
  validations: Validation[];
  pending_id?: string;
  commit?: string;
  transactions?: {
    payee: string;
    from_account: string;
    to_account: string;
    autofilled?: string[];
    display_names: Record<string, string>;
    candidates: Record<string, { account: string; display_name: string }[]>;
  }[];
};
/* budget 节点的回执，同样先预览后确认 */
export type BudgetReceipt = Omit<WriteReceipt, "kind"> & { kind: "budget"; account: string };
/* query 节点的回执 */
export type QueryReceipt = { kind: "query"; tool: string; arguments: any; result: any };
export type Receipt = WriteReceipt | BudgetReceipt | QueryReceipt;

export function classify(event: any): Receipt {
  if (event.tool) return { ...event, kind: "query" };
  if (event.kind === "budget") return { ...event, kind: "budget" };
  return { ...event, kind: "write" };
}

/** 从渲染好的分录文本里把日期/收款方/摘要/账户/金额扒出来，用于事实四宫格。 */
function parseEntry(text: string) {
  const [head = "", ...rest] = text.trim().split("\n");
  const header = head.match(/^(\d{4}-\d{2}-\d{2})\s+\S\s+"([^"]*)"(?:\s+"([^"]*)")?/);
  const postings = rest
    .map((line) => line.trim().match(/^([A-Z][\w:-]+)(?:\s+(-?[\d.,]+)\s+(\w+))?/))
    .filter(Boolean)
    .map((match) => ({ account: match![1], amount: match![2] ?? "", currency: match![3] ?? "" }));
  // Beancount 会省掉其中一条分录的金额，所以金额取「写出来的那条」，账户按符号分方向。
  const written = postings.find((posting) => posting.amount);
  const credit = postings.find((posting) => posting.amount.startsWith("-"));
  const debit = postings.find((posting) => posting !== credit);
  return {
    date: header?.[1] ?? "",
    payee: header?.[2] ?? "",
    narration: header?.[3] ?? "",
    amount: written?.amount ?? "",
    currency: written?.currency ?? "CNY",
    debit: debit?.account ?? "",
    credit: credit?.account ?? "",
  };
}

type Landed = { commit: string; file: string; line: number };

/** 预览态给「确认写入 / 丢弃」，已落盘态给「撤销」。 */
function useWriteActions(pendingId?: string, onLanded?: (landed: Landed) => void) {
  const [busy, setBusy] = useState(false);
  const [landed, setLanded] = useState<Landed | null>(null);
  const [state, setState] = useState<"preview" | "confirmed" | "rejected" | "undone">(
    pendingId ? "preview" : "confirmed",
  );
  const [error, setError] = useState("");

  async function act<T>(run: () => Promise<T>, done: typeof state, then?: (result: T) => void) {
    setBusy(true);
    setError("");
    try {
      const result = await run();
      then?.(result);
      setState(done);
    } catch (reason) {
      setError(String((reason as Error).message));
    } finally {
      setBusy(false);
    }
  }

  return {
    busy,
    error,
    state,
    landed,
    confirm: () =>
      act(() => confirmWrite(pendingId!), "confirmed", (result) => {
        setLanded(result);
        onLanded?.(result);
      }),
    reject: () => act(() => rejectWrite(pendingId!), "rejected"),
    undo: (commit: string) => act(() => undoCommit(commit), "undone"),
  };
}

function Actions({
  receipt,
  actions,
}: {
  receipt: { pending_id?: string; commit?: string };
  actions: ReturnType<typeof useWriteActions>;
}) {
  const commit = actions.landed?.commit ?? receipt.commit;
  if (actions.state === "preview")
    return (
      <>
        <button className="btn primary" disabled={actions.busy} onClick={actions.confirm}>
          确认写入账本
        </button>
        <button className="btn" disabled={actions.busy} onClick={actions.reject}>
          丢弃
        </button>
      </>
    );
  if (actions.state === "rejected") return <div className="linkish">已丢弃，没有写入账本</div>;
  if (actions.state === "undone") return <div className="linkish">已撤销</div>;
  return (
    <button className="btn" disabled={actions.busy || !commit} onClick={() => actions.undo(commit!)}>
      撤销这次写入
    </button>
  );
}

export function WriteCard({ receipt, onLanded, onEdited }: { receipt: WriteReceipt; onLanded?: (landed: Landed) => void; onEdited?: (receipt: WriteReceipt) => void }) {
  const actions = useWriteActions(receipt.pending_id, onLanded);
  const [editing, setEditing] = useState(false);
  const [editError, setEditError] = useState("");
  async function change(index: number, field: "from_account" | "to_account", account: string) {
    setEditing(true);
    setEditError("");
    try {
      const updated = await editWrite(receipt.pending_id!, index, field, account);
      onEdited?.({ ...updated, kind: "write" });
    } catch (reason) {
      setEditError((reason as Error).message);
    } finally {
      setEditing(false);
    }
  }
  const facts = parseEntry(receipt.entries[0] ?? receipt.text ?? "");
  const warnings = receipt.validations?.filter((check) => check.level === "warn") ?? [];

  return (
    <div className={`card accent${warnings.length ? " warn" : ""}`}>
      <div className="body">
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            {actions.state === "preview" ? "待确认交易" : actions.state === "confirmed" ? "已写入账本" : "已丢弃"}
          </div>
          {receipt.balanced && (
            <div className="mono" style={{ fontSize: 10.5, color: "var(--green)" }}>借贷平衡 ✓</div>
          )}
          {receipt.entries.length > 1 && <div className="linkish">共 {receipt.entries.length} 笔</div>}
          <div className="grow" />
          <div className="num" style={{ fontSize: 19 }}>{abs(facts.amount, 2)}</div>
        </div>
        <div className="facts">
          <div className="fact"><span>日期</span><b className="mono">{facts.date}</b></div>
          <div className="fact"><span>收款方</span><b title={facts.payee}>{facts.payee || "—"}</b></div>
          {!receipt.transactions && <>
            <div className="fact"><span>资金流入账户</span><b className="mono" title={facts.debit}>{facts.debit}</b></div>
            <div className="fact"><span>资金流出账户</span><b className="mono" title={facts.credit}>{facts.credit}</b></div>
          </>}
        </div>
        {receipt.transactions?.map((transaction, index) => (
          <div key={index} className="facts">
            <div className="fact"><span>第 {index + 1} 笔</span><b>{transaction.payee}</b></div>
            {(["from_account", "to_account"] as const).map((field) => {
              const options = transaction.candidates[field];
              return <div key={field} className="fact">
                <span>{field === "from_account" ? "资金流出" : "资金流入"}
                  {transaction.autofilled?.includes(field) && <em> · 自动补全</em>}</span>
                {actions.state === "preview" ? <Picker
                  label={`第 ${index + 1} 笔${field === "from_account" ? "资金流出" : "资金流入"}账户`}
                  disabled={editing || actions.busy}
                  value={transaction[field]}
                  onChange={(account) => change(index, field, account)}
                  options={[
                    // 当前选中的账户可能不在候选里（比如上一次手动改过），补一行免得显示空白。
                    ...(options.some((option) => option.account === transaction[field])
                      ? []
                      : [{ value: transaction[field], label: transaction.display_names[field] }]),
                    ...options.map((option) => ({ value: option.account, label: option.display_name })),
                  ]}
                /> : <b>{transaction.display_names[field]}</b>}
              </div>;
            })}
          </div>
        ))}
        {warnings.map((check) => (
          <div key={check.text} style={{ fontSize: 12.5, color: "var(--amber-ink)" }}>
            ! {check.text}
          </div>
        ))}
        {actions.error && <div className="failed">{actions.error}</div>}
        {editError && <div className="failed">{editError}</div>}
      </div>
      <footer>
        <Actions receipt={receipt} actions={{ ...actions, busy: actions.busy || editing }} />
        <div className="grow" />
        <div className="linkish">
          {actions.landed
            ? `${actions.landed.file} · L${actions.landed.line}`
            : `${receipt.file} · L${receipt.insert_at_line} · 右侧为即将写入的 diff →`}
        </div>
      </footer>
    </div>
  );
}

export function BudgetCard({ receipt }: { receipt: BudgetReceipt }) {
  const actions = useWriteActions(receipt.pending_id);
  const warnings = receipt.validations?.filter((check) => check.level === "warn") ?? [];
  return (
    <div className="card accent">
      <div className="body">
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <div style={{ fontSize: 13, fontWeight: 600 }}>
            {actions.state === "preview" ? "待确认的预算" : actions.state === "confirmed" ? "预算已写入账本" : "已丢弃"}
          </div>
          <div className="grow" />
          <div className="linkish">{receipt.file}</div>
        </div>
        <pre className="raw">{receipt.text}</pre>
        {warnings.map((check) => (
          <div key={check.text} style={{ fontSize: 12.5, color: "var(--amber-ink)" }}>
            ! {check.text}
          </div>
        ))}
        {actions.error && <div className="failed">{actions.error}</div>}
      </div>
      <footer>
        <Actions receipt={receipt} actions={actions} />
      </footer>
    </div>
  );
}

/** budget_status 工具的返回：一组预算执行情况。 */
function BudgetRows({ rows }: { rows: any[] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
      {rows.map((row) => {
        const used = Number(row.used ?? 0);
        const limit = Number(row.amount ?? 0);
        const state = budgetState(used, limit);
        return (
          <div className={`card${state === "exceeded" ? " bad" : ""}`} key={row.account}>
            <div className="body">
              <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                <div className="mono" style={{ fontSize: 12 }}>{row.account}</div>
                <div className={`tag ${state}`}>{BUDGET_LABEL[state]}</div>
                <div className="grow" />
                <div className="num" style={{ fontSize: 13 }}>
                  {num(used, 0)} / {num(limit, 0)}
                </div>
              </div>
              <Meter used={used} limit={limit} />
              <div style={{ fontSize: 12.5, color: "var(--ink-2)" }}>
                {row.display_name} · 周期 {row.window?.start} → {row.window?.end} · 剩余 {num(row.remaining ?? 0, 0)}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** group_by 的返回：[{group, amount}]，画成设计稿里的横条。 */
function GroupBars({ rows }: { rows: { group: string; amount: string }[] }) {
  const max = Math.max(1, ...rows.map((row) => Math.abs(Number(row.amount))));
  return (
    <div className="card">
      <header>
        <h3>分组汇总</h3>
        <div className="grow" />
        <div className="linkish">{rows.length} 组</div>
      </header>
      <div className="bars">
        {rows.map((row) => {
          const value = Math.abs(Number(row.amount));
          return (
            <Bar
              key={row.group}
              label={row.group || "—"}
              value={num(value, 0)}
              share={(value / max) * 100}
              peak={value === max}
            />
          );
        })}
      </div>
      <footer>
        <button className="btn sm" disabled title="GET /transactions/export.csv 尚未实现">
          导出 CSV
        </button>
      </footer>
    </div>
  );
}

function TransactionRows({ rows }: { rows: any[] }) {
  const total = rows.reduce((sum, row) => {
    const expense = row.postings?.find((posting: any) => posting.account?.startsWith("Expenses:"));
    return sum + Math.abs(Number(expense?.amount ?? row.postings?.[0]?.amount ?? 0));
  }, 0);
  return (
    <div className="card">
      <header>
        <h3>命中 {rows.length} 笔</h3>
        <div className="grow" />
        <div className="linkish">支出合计 {num(total, 2)}</div>
      </header>
      <div style={{ padding: "10px 15px", display: "flex", flexDirection: "column", gap: 7 }}>
        {rows.slice(0, 12).map((row, index) => {
          const posting = row.postings?.find((item: any) => item.account?.startsWith("Expenses:")) ?? row.postings?.[0];
          return (
            <div key={index} style={{ display: "flex", gap: 12, font: "11.5px var(--mono)", color: "#3A332A" }}>
              <span style={{ width: 82, flex: "none", color: "var(--ink-3)" }}>{row.date?.slice(5)}</span>
              <span className="grow" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {[row.payee, row.narration].filter(Boolean).join(" · ") || "—"}
              </span>
              <span>{posting?.amount ? num(posting.amount, 2) : "—"}</span>
            </div>
          );
        })}
      </div>
      {rows.length > 12 && <footer><div className="linkish">其余 {rows.length - 12} 笔见下方原始返回</div></footer>}
    </div>
  );
}

function Balances({ balances }: { balances: Record<string, Record<string, string>> }) {
  const entries = Object.entries(balances);
  return (
    <div className="card">
      <header><h3>余额</h3><div className="grow" /><div className="linkish">{entries.length} 个账户</div></header>
      <div style={{ padding: "10px 15px", display: "flex", flexDirection: "column", gap: 7 }}>
        {entries.map(([account, amounts]) => (
          <div key={account} style={{ display: "flex", gap: 12, font: "11.5px var(--mono)" }}>
            <span className="grow" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{account}</span>
            {Object.entries(amounts).map(([currency, amount]) => (
              <span key={currency}>{num(amount, 2)} {currency}</span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function QueryCard({ receipt }: { receipt: QueryReceipt }) {
  const result = receipt.result;
  const isBudget = Array.isArray(result) && result.length > 0 && "used" in result[0] && "amount" in result[0];
  const isGroup = Array.isArray(result) && result.length > 0 && "group" in result[0];
  const isRows = Array.isArray(result) && result.length > 0 && "postings" in result[0];
  const isAccounts = Array.isArray(result) && result.length > 0 && "display_name" in result[0] && !("used" in result[0]);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 13 }}>
      <div className="card">
        <Disclose label={`${receipt.tool} 的参数`} defaultOpen>
          <div className="io" style={{ gridTemplateColumns: "1fr", borderTop: 0 }}>
            <div>
              <div className="kicker">arguments</div>
              <pre>{JSON.stringify(receipt.arguments, null, 2)}</pre>
            </div>
          </div>
        </Disclose>
      </div>
      {isBudget && <BudgetRows rows={result} />}
      {isGroup && <GroupBars rows={result} />}
      {isRows && <TransactionRows rows={result} />}
      {isAccounts && (
        <div className="card">
          <header><h3>账户 {result.length} 个</h3></header>
          <div style={{ padding: "10px 15px", display: "flex", flexDirection: "column", gap: 6 }}>
            {result.map((row: any) => (
              <div key={row.account} style={{ display: "flex", gap: 10, font: "11.5px var(--mono)" }}>
                <span className="grow">{row.account}</span>
                <span className="muted">{row.display_name ?? ""}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      {!Array.isArray(result) && typeof result === "object" && result && !("error" in result) && (
        <Balances balances={result} />
      )}
      {Array.isArray(result) && result.length === 0 && <div className="hollow">这个范围内没有找到记录。</div>}
    </div>
  );
}

export function ReceiptCard({ receipt, onLanded, onEdited }: { receipt: Receipt; onLanded?: (landed: Landed) => void; onEdited?: (receipt: WriteReceipt) => void }) {
  if (receipt.kind === "write") return <WriteCard receipt={receipt} onLanded={onLanded} onEdited={onEdited} />;
  if (receipt.kind === "budget") return <BudgetCard receipt={receipt} />;
  return <QueryCard receipt={receipt} />;
}