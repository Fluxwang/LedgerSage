/**
 * 前端到后端的唯一出口。
 *
 * 设计稿要求的数据里有一部分后端还没有对应端点：这些函数一律走 `pending()`，
 * 抛出 `MissingEndpoint`，由界面渲染成「待接口」占位而不是假数据。
 * 完整清单见 docs/archive/ledgersage-frontend/missing-endpoints.md。
 */

const TOKEN_KEY = "beanchat_token";

export const token = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (value: string) => localStorage.setItem(TOKEN_KEY, value);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

/** 设计稿需要、后端尚未提供的端点。界面捕获它并渲染占位卡。 */
export class MissingEndpoint extends Error {
  constructor(
    readonly endpoint: string,
    readonly why: string,
  ) {
    super(`${endpoint} 尚未实现`);
    this.name = "MissingEndpoint";
  }
}

function pending(endpoint: string, why: string): never {
  throw new MissingEndpoint(endpoint, why);
}

async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token() ? { Authorization: `Bearer ${token()}` } : {}),
      ...options.headers,
    },
  });
  if (response.status === 401) {
    clearToken();
    location.reload();
  }
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || `请求失败（${response.status}）`);
  }
  return response.json();
}

/* ------------------------------------------------------------------ 已有端点 */

export type Me = { id: string; username: string };
export type AccountName = { account: string; display_name: string | null };
export type Posting = { account: string; amount: string | null; currency: string | null };
export type Row = { date: string; payee: string | null; narration: string; postings: Posting[] };
export type Card = {
  account: string;
  display_name: string;
  kind: "asset" | "liability";
  balance: string;
  change: string;
  currency: string;
};
export type Budget = {
  account: string;
  display_name: string;
  amount: string;
  used: string;
  remaining: string;
  currency: string;
  period: string;
  window: { start: string; end: string };
};
export type Dashboard = {
  accounts: Card[];
  monthly_trend: { month: string; amount: string }[];
  categories: { account: string; display_name: string; amount: string }[];
  top_payees: { payee: string; amount: string }[];
  recent: { rows: Row[]; page: number; size: number; total: number };
  budgets: Budget[];
  period: { start: string; end: string; name: string };
};

export const auth = {
  login: (body: { username: string; password: string }) =>
    api<{ access_token: string }>("/auth/login", { method: "POST", body: JSON.stringify(body) }),
  register: (body: { username: string; password: string; invite_code: string }) =>
    api<{ access_token: string }>("/auth/register", { method: "POST", body: JSON.stringify(body) }),
  me: () => api<Me>("/auth/me"),
};

export const dashboard = (period: string, page = 1) =>
  api<Dashboard>(`/dashboard?period=${encodeURIComponent(period)}&page=${page}`);

export const accounts = (prefix = "") =>
  api<AccountName[]>(`/accounts?prefix=${encodeURIComponent(prefix)}`);

export const undoCommit = (commit: string) =>
  api<{ status: string }>(`/transactions/${commit}/undo`, { method: "POST" });

export const runs = {
  list: (query: string) => api<{ rows: any[]; total: number }>(`/runs?${query}`),
  detail: (id: string) => api<any>(`/runs/${id}`),
};

export const vector = {
  status: () => api<any>("/admin/vector/status"),
  rebuild: () => api<any>("/admin/vector/rebuild", { method: "POST" }),
  cancel: () => api<any>("/admin/vector/rebuild/cancel", { method: "POST" }),
};

/* ---------------------------------------------------------------- 待补端点 */

export type LedgerStatus = {
  bean_check: { ok: boolean; error_count: number; message: string };
  git: { clean: boolean; last_commit_at: string | null };
  health: { key: "bean_check" | "working_tree" | "missing_payee"; level: "ok" | "warn"; text: string }[];
};

/** 顶栏与右栏共用的账本健康度，独立于仪表盘和统计区间。 */
export const ledgerStatus = () => api<LedgerStatus>("/ledger/status");

export type LedgerSlice = { file: string; start_line: number; lines: string[] };

/** 右栏「即将写入的 diff」上下文，以及「查询命中的原始条目」。 */
export const ledgerSlice = (_params: { file?: string; around?: number; context?: number }): Promise<LedgerSlice> =>
  pending("GET /ledger/raw", "右栏要展示写入位置前后的账本原文");

export type Validation = { level: "ok" | "warn"; text: string };

/** 两段式写入（ADR 0012）：SSE 的 receipt 是预览，确认之后才有 commit。 */
export const confirmWrite = (id: string) =>
  api<{ commit: string; file: string; line: number; entries?: string[] }>(
    `/chat/pending/${id}/confirm`,
    { method: "POST" },
  );

export const rejectWrite = (id: string) =>
  api<{ status: string }>(`/chat/pending/${id}/reject`, { method: "POST" });

export const editWrite = (id: string, transactionIndex: number, field: "from_account" | "to_account", account: string) =>
  api<import("./chat/Results").WriteReceipt>(`/chat/pending/${id}`, {
    method: "PATCH", body: JSON.stringify({ transaction_index: transactionIndex, [field]: account }),
  });

export type Session = { thread_id: string; title: string; last_active_at: string; has_pending_ask: boolean };

/** 最近 30 个对话，选择后沿用原来的 thread_id。 */
export const sessions = (): Promise<Session[]> =>
  api("/sessions");

export type SessionReplay = { active_run_id: string | null; pending_at: string | null; has_pending_ask: boolean; ask_expired: boolean; runs: any[] };
export const sessionRuns = (threadId: string): Promise<SessionReplay> =>
  api(`/sessions/${encodeURIComponent(threadId)}/runs`);

export type AccountNode = {
  account: string;
  display_name: string;
  depth: number;
  amount: string;
  children?: AccountNode[];
};

/** 统计页左栏账户树：带层级与区间金额。/accounts 只返回名字。 */
export const accountTree = (_params: { start: string; end: string }): Promise<AccountNode[]> =>
  pending("GET /accounts/tree", "账户树要带层级与区间内的发生额");

export type StatementCell = { period: string; amount: string };
export type StatementRow = { account: string; display_name: string; depth: number; cells: StatementCell[] };
export type IncomeStatement = {
  periods: string[];
  rows: StatementRow[];
  totals: { expense: string; income: string; net: string; savings_rate: string; peak: StatementCell };
  composition: { period: string; parts: { account: string; display_name: string; amount: string }[] }[];
};

/** 收支表：按账户 × 月的矩阵 + 堆叠构成。/dashboard 只给单区间的分类合计。 */
export const incomeStatement = (_params: { start: string; end: string; account?: string; tag?: string }): Promise<IncomeStatement> =>
  pending("GET /statements/income", "收支表要按账户层级 × 多个月出矩阵");

export type BalanceSheet = {
  as_of: string;
  currency: string;
  net_worth: string;
  net_worth_change: string;
  assets: string;
  liabilities: string;
  liquidity_months: string;
  trend: { period: string; net_worth: string; liabilities: string }[];
  rows: StatementRow[];
  allocation: { account: string; display_name: string; amount: string; share: string }[];
  reconciliation: { account: string; date: string; amount: string; currency: string; ok: boolean; stale_days: number }[];
};

/** 资产负债：期末余额、净资产走势、配置占比、balance 指令对账状态。 */
export const balanceSheet = (_params: { as_of: string; months: number }): Promise<BalanceSheet> =>
  pending("GET /statements/balance", "资产负债页要期末余额、净资产走势与 balance 对账");

export type Transaction = Row & {
  id: string;
  tags: string[];
  amount: string;
  currency: string;
  account: string;
  from: string;
  flagged: boolean;
};

export const transactions = (params: {
  start?: string;
  end?: string;
  account?: string;
  tag?: string;
  payee?: string;
  page: number;
  size: number;
}) => {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params))
    if (value) query.set(key, String(value));
  return api<{ rows: Transaction[]; page: number; size: number; total: number; sum: string; currency: string }>(
    `/transactions?${query}`,
  );
};

export const transactionRaw = (id: string) =>
  api<{ file: string; start_line: number; end_line: number; text: string }>(
    `/transactions/${id}/raw`,
  );

/** 删除会改写账本原文——纯追加写入之外的唯一例外，见 ADR 0013。 */
export const deleteTransaction = (id: string) =>
  api<{ commit: string; file: string; removed_lines: number; text: string }>(
    `/transactions/${id}`,
    { method: "DELETE" },
  );

export type SavedQuery = { id: string; question: string; created_at: string };

export const savedQueries = {
  list: () => api<SavedQuery[]>("/saved-queries"),
  create: (body: { run_id: string }) =>
    api<SavedQuery>("/saved-queries", { method: "POST", body: JSON.stringify(body) }),
  remove: (id: string) => api<{ status: string }>(`/saved-queries/${encodeURIComponent(id)}`, { method: "DELETE" }),
};

export type MonthlyReport = {
  month: string;
  compare_to: string;
  income: { amount: string; delta: string };
  expense: { amount: string; delta: string };
  savings_rate: { value: string; delta: string };
  composition: { display_name: string; amount: string; share: string }[];
  net_cash_flow: { period: string; amount: string }[];
  deltas: { display_name: string; amount: string }[];
  summary: string;
};

/** 月度报表场景。目前 Agent 没有 monthly_report 工具，也没有导出端点。 */
export const monthlyReport = (_params: { month: string; compare_to: string }): Promise<MonthlyReport> =>
  pending("GET /reports/monthly", "月度报表场景缺少后端聚合与 Agent 工具");

export const exportReport = (_params: { month: string; format: "pdf" | "markdown" }): Promise<{ url: string }> =>
  pending("POST /reports/export", "「导出 PDF」「写入 reports/*.md」没有落点");

export const exportTransactionsCsv = (_params: { start: string; end: string; account?: string }): Promise<Blob> =>
  pending("GET /transactions/export.csv", "查询结果卡上的「导出 CSV」没有端点");

export const suggestions = (): Promise<string[]> =>
  pending("GET /suggestions", "输入框上方的建议 chips 目前是前端写死的");
