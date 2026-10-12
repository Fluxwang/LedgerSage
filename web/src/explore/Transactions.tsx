import { useEffect, useMemo, useRef, useState } from "react";
import {
  type Dashboard,
  deleteTransaction,
  type Transaction,
  transactionRaw,
  transactions as fetchTransactions,
  undoCommit,
} from "../api";
import { Async, num, useAsync } from "../ui";

/** 一次只取 30 条；滚到底再要下一批。 */
const TX_PAGE_SIZE = 30;

type Feed = {
  rows: Transaction[];
  /** 已经取到第几页，0 表示还没有第一页 */
  page: number;
  total: number;
  sum: string;
  currency: string;
};

const EMPTY_FEED: Feed = {
  rows: [],
  page: 0,
  total: 0,
  sum: "0",
  currency: "CNY",
};

function DeleteFlow({
  row,
  onClose,
  onDeleted,
}: {
  row: Transaction;
  onClose: () => void;
  onDeleted: (commit: string, label: string) => void;
}) {
  const raw = useAsync(() => transactionRaw(row.id), [row.id]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function confirm() {
    setBusy(true);
    setError("");
    try {
      const { commit } = await deleteTransaction(row.id);
      onDeleted(
        commit,
        `${row.date} · ${row.payee || row.narration} · ${num(row.amount, 2)} ${row.currency}`,
      );
      onClose();
    } catch (reason) {
      setError(String((reason as Error).message));
      setBusy(false);
    }
  }

  return (
    <div className="scrim" onClick={onClose}>
      <div className="modal" onClick={(event) => event.stopPropagation()}>
        <div className="in">
          <h3>删除这笔账目？</h3>
          <p>
            下面这段将从账本原文中移除。删除后可以撤销，git 提交前不会落到远端。
          </p>
          <Async state={raw}>
            {(slice) => (
              <pre>
                {slice.text
                  .split("\n")
                  .map((line) => `- ${line}`)
                  .join("\n")}
              </pre>
            )}
          </Async>
          {error && <div className="failed">{error}</div>}
        </div>
        <footer>
          <div className="linkish">
            {raw.data ? `${raw.data.file} · L${raw.data.start_line}` : row.date}
          </div>
          <div className="grow" />
          <button className="btn" onClick={onClose}>
            取消
          </button>
          <button
            className="btn danger"
            disabled={busy || !raw.data}
            onClick={confirm}
          >
            确认删除
          </button>
        </footer>
      </div>
    </div>
  );
}

export function Transactions({
  period,
  filter,
  budgets,
  onLedgerChanged,
}: {
  period: { start: string; end: string };
  filter: { account: string; text: string };
  budgets: Dashboard["budgets"];
  onLedgerChanged: () => void;
}) {
  const [target, setTarget] = useState<Transaction | null>(null);
  const [undone, setUndone] = useState<{
    commit: string;
    label: string;
  } | null>(null);
  const [deleted, setDeleted] = useState(0);
  /** 账本被改动过就整表重来，不在已加载的几页上打补丁。 */
  const [epoch, setEpoch] = useState(0);
  const [feed, setFeed] = useState<Feed>(EMPTY_FEED);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const sentinel = useRef<HTMLDivElement>(null);
  /** 只认最新一组筛选条件的响应，旧请求回来晚了就丢掉。 */
  const ticket = useRef(0);

  const { start, end } = period;
  const { account, text } = filter;
  const query = useMemo(
    () => ({ start, end, account, payee: text }),
    [start, end, account, text],
  );

  // 换筛选条件或账本变动：丢掉已加载的几页，从第一页重新开始。
  useEffect(() => {
    const mine = ++ticket.current;
    setFeed(EMPTY_FEED);
    setError("");
    setBusy(true);
    if (scroller.current) scroller.current.scrollTop = 0;
    fetchTransactions({ ...query, page: 1, size: TX_PAGE_SIZE })
      .then((data) => {
        if (ticket.current !== mine) return;
        setFeed({
          rows: data.rows,
          page: 1,
          total: data.total,
          sum: data.sum,
          currency: data.currency,
        });
      })
      .catch((reason) => {
        if (ticket.current === mine)
          setError(String((reason as Error).message));
      })
      .finally(() => {
        if (ticket.current === mine) setBusy(false);
      });
  }, [query, epoch]);

  const more = feed.page > 0 && feed.rows.length < feed.total;

  // 滚到列表底部才要下一批；停在原地就不再发请求。
  useEffect(() => {
    const anchor = sentinel.current;
    const root = scroller.current;
    if (!anchor || !root || !more || busy) return;
    const mine = ticket.current;
    const next = feed.page + 1;
    const observer = new IntersectionObserver(
      async ([entry]) => {
        if (!entry.isIntersecting) return;
        observer.disconnect();
        setBusy(true);
        try {
          const data = await fetchTransactions({
            ...query,
            page: next,
            size: TX_PAGE_SIZE,
          });
          if (ticket.current !== mine) return;
          setFeed((prev) => {
            const rows = [...prev.rows, ...data.rows];
            return {
              ...prev,
              rows,
              page: next,
              // 后端没再给出行，就按已加载的条数收口，免得空转
              total: data.rows.length ? data.total : rows.length,
              sum: data.sum,
            };
          });
        } catch (reason) {
          if (ticket.current === mine)
            setError(String((reason as Error).message));
        } finally {
          if (ticket.current === mine) setBusy(false);
        }
      },
      { root, rootMargin: "160px" },
    );
    observer.observe(anchor);
    return () => observer.disconnect();
  }, [more, busy, feed.page, query]);

  function reload() {
    setDeleted((count) => count + 1);
    setEpoch((value) => value + 1);
    onLedgerChanged();
  }

  async function undo(commit: string) {
    await undoCommit(commit);
    setUndone(null);
    reload();
  }

  const missing = feed.rows.filter((row) => !row.payee).length;
  if (error) return <div className="failed">{error}</div>;
  if (busy && feed.page === 0) return <div className="loading">读取账本…</div>;

  return (
    <>
      <div className="kpis">
        <div className="kpi">
          <span>当前筛选笔数</span>
          <b>{feed.total}</b>
          <em>
            {period.start} → {period.end}
          </em>
        </div>
        <div className="kpi">
          <span>合计</span>
          <b>{num(feed.sum, 2)}</b>
          <em>{feed.currency}</em>
        </div>
        <div className="kpi">
          <span>已加载待补收款方</span>
          <b>{missing}</b>
          <em>来自导入</em>
        </div>
        <div className="kpi">
          <span>本次会话已删除</span>
          <b>{deleted}</b>
          <em>可撤销</em>
        </div>
      </div>

      <div className="card">
        <header>
          <h3>流水 · 按日期倒序</h3>
          <div className="grow" />
          <div className="linkish">删除会在账本原文中移除整笔交易</div>
        </header>
        <div className="txfeed" ref={scroller}>
          <div className="txgrid head">
            <div>日期</div>
            <div>收款方 · 摘要</div>
            <div>账户</div>
            <div>标签</div>
            <div style={{ textAlign: "right" }}>金额</div>
            <div style={{ textAlign: "right" }}>操作</div>
          </div>
          {feed.rows.map((row) => (
            <div className="txgrid" key={row.id}>
              <div className="date">{row.date}</div>
              <div className="who">
                <b>{row.payee || "（未识别收款方）"}</b>
                <small>{row.narration}</small>
              </div>
              <div className="acct">
                <div title={row.account}>→ {row.account}</div>
                <div title={row.from}>← {row.from}</div>
              </div>
              <div className="mono" style={{ fontSize: 11 }}>
                {row.tags.length
                  ? row.tags.map((tag) => `#${tag}`).join(" ")
                  : "—"}
              </div>
              <div className={`amt${row.payee ? "" : " flag"}`}>
                {num(row.amount, 2)}
              </div>
              <div className="ops">
                <button
                  className="btn sm"
                  onClick={() => setTarget(row)}
                  title="删除这笔账目"
                >
                  删除
                </button>
              </div>
            </div>
          ))}
          {feed.rows.length === 0 && (
            <div className="hollow">当前筛选下没有账目了。</div>
          )}
          {more && (
            <div className="txmore" ref={sentinel}>
              {busy ? "读取下一批…" : "继续下滑加载更多"}
            </div>
          )}
        </div>
        <footer>
          <div className="linkish">
            已加载 {feed.rows.length} / {feed.total} 笔 · 每批 {TX_PAGE_SIZE} 条
          </div>
          <div className="grow" />
          <div className="linkish">{budgets.length} 条预算在右栏</div>
        </footer>
      </div>

      {target && (
        <DeleteFlow
          row={target}
          onClose={() => setTarget(null)}
          onDeleted={(commit, label) => {
            setUndone({ commit, label });
            reload();
          }}
        />
      )}
      {undone && (
        <div className="toast">
          <div>已删除 {undone.label}</div>
          <small>账本原文已更新 · git 已提交</small>
          <div className="grow" />
          <button className="btn" onClick={() => undo(undone.commit)}>
            撤销
          </button>
          <button className="btn ghost" onClick={() => setUndone(null)}>
            ✕
          </button>
        </div>
      )}
    </>
  );
}
