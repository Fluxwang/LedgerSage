import "./chat.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { clearToken, deleteSession, type Dashboard, token, sessions, sessionRuns, type Session, type SessionReplay } from "../api";
import { abs, num } from "../ui";
import { LedgerPanel } from "./LedgerPanel";
import type { LedgerHealthState } from "../shell/LedgerHealth";
import { classify, ReceiptCard, type Receipt, type WriteReceipt } from "./Results";
import { type Step, ToolTrace, traceSummary } from "./ToolTrace";
import { ConversationItem } from "./ConversationItem";

type Turn = {
  said?: string;
  steps: Step[];
  receipts: Receipt[];
  reply?: string;
  ask?: { question: string; candidates: string[] };
  note?: string;
  error?: string;
  running: boolean;
  replay?: boolean;
  askActive?: boolean;
};

/** 运行是回放单位；只从公开的步骤和当前待确认写入重建，不读 checkpoint。 */
function replayTurns(data: SessionReplay): Turn[] {
  return data.runs.map((run) => {
    const steps: Step[] = run.steps.map((step: any) => ({ ...step, node:
      step.kicker === "CLASSIFY" ? "classify" : step.kicker === "PARSE" ? "extract" :
      step.kicker === "REPLY" ? "reply" : step.kicker === "ASK" ? "prepare_ask" :
      step.payload.receipt?.tool ? "query" : step.payload.receipt?.kind === "budget" ? "budget" : "tools" }));
    const receipts = steps.filter((step) => step.payload?.receipt).map((step) => {
      const receipt = { ...step.payload.receipt, run_id: run.id };
      const pending = run.pending_writes.find((item: any) => item.id === receipt.pending_id);
      return classify(pending ? { ...receipt, ...(pending.receipt ?? {}), replay_status: pending.status, preview_error: pending.preview_error, commit: pending.commit_sha ?? undefined } : receipt);
    });
    const asks = steps.filter((step) => step.payload?.ask);
    const ask = asks.at(-1)?.payload.ask;
    const active = data.active_run_id === run.id && data.has_pending_ask;
    return { said: run.message || run.title, steps, receipts,
      reply: steps.filter((step) => step.kicker === "REPLY").at(-1)?.payload.message,
      ask, askActive: active, replay: true,
      note: ask ? active ? "追问中" : (data.active_run_id === run.id && data.ask_expired) || run.status === "clarification" || run.status === "failed" ? "追问已作废" : "追问已答复" : undefined,
      error: run.status === "failed" && !ask ? "这次运行失败" : run.status === "interrupted" ? "这次运行已中断" : undefined,
      running: false };
  });
}

const SUGGESTIONS = ["昨天的地铁 6 块", "这个月餐饮花了多少", "把餐饮预算设成 1500"];

/** 后端 SSE 是 `event:`+`data:` 双行帧，这里只取 data 行。 */
async function* frames(body: ReadableStream<Uint8Array>) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((item) => item.startsWith("data: "));
      if (line) yield JSON.parse(line.slice(6));
    }
  }
}

export function Chat({
  data,
  health,
  seed,
  onLedgerChanged,
  onSeedConsumed,
}: {
  data?: Dashboard;
  health: LedgerHealthState;
  seed?: { text: string; nonce: number; autoSend?: boolean };
  onLedgerChanged: () => void;
  onSeedConsumed: () => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [running, setRunning] = useState(false);
  const [thread, setThread] = useState<string>(() => crypto.randomUUID());
  const [history, setHistory] = useState<Session[]>([]);
  const [historyError, setHistoryError] = useState("");
  const [loading, setLoading] = useState(false);
  const [pendingAsk, setPendingAsk] = useState(false);
  const generation = useRef(0);
  const historyRequest = useRef(0);
  const currentThread = useRef(thread);
  currentThread.current = thread;
  const renderedGeneration = generation.current;
  const stream = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  async function refreshHistory() {
    const request = ++historyRequest.current;
    try {
      const rows = await sessions();
      if (request === historyRequest.current) { setHistory(rows); setHistoryError(""); }
    } catch (error) { if (request === historyRequest.current) setHistoryError((error as Error).message); }
  }
  useEffect(() => { void refreshHistory(); }, []);

  function newConversation() {
    generation.current++;
    setLoading(false); setPendingAsk(false); setText("");
    setTurns([]);
    const id = crypto.randomUUID();
    currentThread.current = id;
    setThread(id);
  }

  async function removeConversation(id: string) {
    // 确认或丢弃写入后笔数可能变化，弹框之前重新读取当前状态。
    const latest = await sessions();
    const item = latest.find((row) => row.thread_id === id);
    if (!item) throw new Error("对话不存在，请刷新列表");
    const pending = item.pending_write_count > 0
      ? `\n其中 ${item.pending_write_count} 笔待确认的记账会一并丢弃。` : "";
    if (!window.confirm(`删除对话「${item.title}」？账本不受影响。${pending}`)) return;
    await deleteSession(id);
    historyRequest.current++;
    setHistory((items) => items.filter((row) => row.thread_id !== id));
    if (currentThread.current === id) newConversation();
  }

  async function openSession(id: string) {
    if (running) return;
    const current = ++generation.current;
    setLoading(true);
    setHistoryError("");
    try {
      const replay = await sessionRuns(id);
      if (current !== generation.current) return;
      setThread(id); setTurns(replayTurns(replay)); setPendingAsk(replay.has_pending_ask); setText("");
    } catch (error) { if (current === generation.current) setHistoryError((error as Error).message); }
    finally { if (current === generation.current) setLoading(false); }
  }

  // 常用查询直接重问，其余统计页入口仍只填入输入框。
  useEffect(() => {
    if (!seed || running || loading) return;
    // 清理尚未执行的任务，避免 StrictMode 的额外挂载重复发送。
    const timer = window.setTimeout(() => {
      if (seed.autoSend) void send(seed.text);
      else {
        setText(seed.text);
        box.current?.focus();
      }
      onSeedConsumed();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [seed?.nonce, running, loading]);

  useEffect(() => {
    stream.current?.scrollTo({ top: stream.current.scrollHeight, behavior: "smooth" });
  }, [turns]);

  const lastWrite = useMemo(() => {
    for (let index = turns.length - 1; index >= 0; index--) {
      const write = [...turns[index].receipts].reverse().find((receipt) => receipt.kind === "write");
      if (write) return write as WriteReceipt;
    }
    return undefined;
  }, [turns]);

  /** 确认写入之后把回执换成落盘后的那份，右栏跟着从「即将写入」变成「已写入」。 */
  const land = (turnIndex: number, position: number, landed: { commit: string; file: string; line: number }) => {
    onLedgerChanged();
    void refreshHistory();
    if (generation.current !== renderedGeneration) return;
    setTurns((items) =>
      items.map((turn, index) =>
        index !== turnIndex
          ? turn
          : {
              ...turn,
              receipts: turn.receipts.map((receipt, slot) =>
                slot === position
                  ? { ...receipt, commit: landed.commit, file: landed.file, insert_at_line: landed.line }
                  : receipt,
              ),
            },
      ),
    );
  };

  /** 每个事件只改最后一个 turn，保证流式过程中不重排前面的内容。 */
  const patch = (change: (turn: Turn) => Turn) =>
    setTurns((items) => items.map((turn, index) => (index === items.length - 1 ? change(turn) : turn)));

  async function send(value = text) {
    const message = value.trim();
    if (!message || running || loading) return;
    setPendingAsk(false);
    setText("");
    setRunning(true);
    setTurns((items) => [...items, { said: message, steps: [], receipts: [], running: true }]);
    try {
      const response = await fetch("/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify({ message, thread_id: thread }),
      });
      if (response.status === 401) {
        clearToken();
        location.reload();
        return;
      }
      if (!response.ok) {
        const error = await response.json().catch(() => ({}));
        throw new Error(error.detail || `请求失败（${response.status}）`);
      }
      if (!response.body) throw new Error("服务端没有返回事件流");
      for await (const event of frames(response.body)) {
        if (event.type === "step")
          patch((turn) => ({
            ...turn,
            steps: [
              ...turn.steps,
              { node: event.node, kicker: event.kicker, title: event.title, duration_ms: event.duration_ms, payload: event.payload },
            ],
          }));
        else if (event.type === "message") patch((turn) => ({ ...turn, reply: event.content }));
        else if (event.type === "receipt")
          patch((turn) => ({ ...turn, receipts: [...turn.receipts, classify(event)] }));
        else if (event.type === "ask") {
          setPendingAsk(true);
          patch((turn) => ({ ...turn, ask: { question: event.question, candidates: event.candidates ?? [] } }));
        }
        else if (event.type === "error") patch((turn) => ({ ...turn, error: event.detail }));
      }
    } catch (reason) {
      patch((turn) => ({ ...turn, error: `连接中断：${String((reason as Error).message ?? reason)}` }));
    } finally {
      patch((turn) => ({ ...turn, running: false }));
      setRunning(false);
      void refreshHistory();
    }
  }

  const roots = useMemo(() => {
    if (!data) return [];
    const sum = (prefix: string) =>
      data.accounts.filter((card) => card.account.startsWith(prefix)).reduce((total, card) => total + Number(card.balance), 0);
    const expenses = data.categories.reduce((total, item) => total + Number(item.amount), 0);
    return [
      ["Assets", num(sum("Assets:"), 0)],
      ["Liabilities", num(sum("Liabilities:"), 0)],
      ["Expenses", abs(expenses, 0)],
    ] as [string, string][];
  }, [data]);

  return (
    <div className="chat">
      <aside className="rail">
        <div className="rail-group">
          <div className="kicker">对话</div>
          {!history.some((item) => item.thread_id === thread) && <button className="rail-item on">本次对话</button>}
          <button
            className="rail-item"
            disabled={running}
            onClick={newConversation}
          >
            ＋ 新对话
          </button>
          {history.map((item) => (
            <ConversationItem
              key={item.thread_id}
              item={item}
              active={item.thread_id === thread}
              running={running}
              onOpen={() => void openSession(item.thread_id)}
              onRenamed={(title) => {
                historyRequest.current++;
                setHistory((items) => items.map((row) => row.thread_id === item.thread_id ? { ...row, title } : row));
              }}
              onDelete={() => removeConversation(item.thread_id)}
            />
          ))}
          {historyError && <div className="failed" role="alert">{historyError}</div>}
        </div>
        <div className="rail-group">
          <div className="kicker">账本</div>
          {roots.map(([name, amount]) => (
            <div className="rail-row" key={name}>
              <span>{name}</span>
              <span>{amount}</span>
            </div>
          ))}
          {roots.length === 0 && <div className="rail-row"><span>读取中…</span></div>}
        </div>
        <div className="grow" />
      </aside>

      <section className="convo">
        <div className="stream" ref={stream}>
          {loading && <div className="sysnote">读取历史对话…</div>}
          {turns.length === 0 && (
            <div className="welcome">
              <h2>今天想记点什么？</h2>
              <p>可以说「午饭 38，微信」，也可以问「这个月餐饮花了多少」。</p>
            </div>
          )}
          {turns.map((turn, index) => (
            <article className="turn" key={`${thread}-${generation.current}-${index}-${turn.replay ? "replay" : "live"}`}>
              {turn.said && (
                <div className="said">
                  <div>{turn.said}</div>
                </div>
              )}
              {turn.note && <div className="sysnote">{turn.note}</div>}
              <div className="reply">
                <header>
                  <i />
                  <b>LedgerSage</b>
                  <small>{traceSummary(turn.steps, turn.running)}</small>
                </header>
                <ToolTrace steps={turn.steps} running={turn.running} />
                {turn.receipts.map((receipt, position) => (
                  <ReceiptCard
                    receipt={receipt}
                    canSave={!turn.running && !turn.error}
                    key={position}
                    onLanded={(landed) => land(index, position, landed)}
                    onUndone={onLedgerChanged}
                    onEdited={(updated) => { if (generation.current !== renderedGeneration) return; setTurns((items) => items.map((item, turnIndex) =>
                      turnIndex === index ? { ...item, receipts: item.receipts.map((old, slot) => slot === position ? updated : old) } : item
                    )); }}
                  />
                ))}
                {turn.ask && (
                  <div className="card warn">
                    <div className="body">
                      <div className="prose">{turn.ask.question}</div>
                      <div className="suggest">
                        {turn.ask.candidates.map((candidate) => (
                          <button key={candidate} disabled={running || loading || (turn.replay && !turn.askActive)} onClick={() => send(candidate)}>
                            {candidate}
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
                {turn.reply && <div className="prose">{turn.reply}</div>}
                {turn.error && <div className="failed">{turn.error}</div>}
              </div>
            </article>
          ))}
        </div>

        <div className="composer">
          {pendingAsk && <div className="sysnote">上次的追问还在等你回答</div>}
          <div className="suggest">
            {SUGGESTIONS.map((item) => (
              <button key={item} onClick={() => send(item)} disabled={running || loading}>
                {item}
              </button>
            ))}
          </div>
          <div className="inputbox">
            <textarea
              ref={box}
              disabled={loading}
              value={text}
              rows={1}
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                  event.preventDefault();
                  send();
                }
              }}
              placeholder="用一句话记账，或问账本任何问题…"
            />
            <button className="btn primary" onClick={() => send()} disabled={running || loading || !text.trim()}>
              {running ? "运行中…" : "发送"}
            </button>
            <kbd>⌘↵</kbd>
          </div>
        </div>
      </section>

      <LedgerPanel receipt={lastWrite} data={data} health={health} file={lastWrite?.file ?? "ledger/"} />
    </div>
  );
}
