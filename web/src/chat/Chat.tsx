import "./chat.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { clearToken, type Dashboard, token } from "../api";
import { abs, num } from "../ui";
import { LedgerPanel } from "./LedgerPanel";
import { classify, ReceiptCard, type Receipt, type WriteReceipt } from "./Results";
import { type Step, ToolTrace, traceSummary } from "./ToolTrace";

type Turn = {
  said?: string;
  steps: Step[];
  receipts: Receipt[];
  reply?: string;
  ask?: { question: string; candidates: string[] };
  note?: string;
  error?: string;
  running: boolean;
};

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
  seed,
  onLedgerChanged,
  onSeedConsumed,
}: {
  data?: Dashboard;
  seed?: { text: string; nonce: number; autoSend?: boolean };
  onLedgerChanged: () => void;
  onSeedConsumed: () => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [running, setRunning] = useState(false);
  const [thread, setThread] = useState(() => crypto.randomUUID());
  const stream = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  // 常用查询直接重问，其余统计页入口仍只填入输入框。
  useEffect(() => {
    if (!seed || running) return;
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
  }, [seed?.nonce, running]);

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
    if (!message || running) return;
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
        else if (event.type === "ask")
          patch((turn) => ({ ...turn, ask: { question: event.question, candidates: event.candidates ?? [] } }));
        else if (event.type === "error") patch((turn) => ({ ...turn, error: event.detail }));
      }
    } catch (reason) {
      patch((turn) => ({ ...turn, error: `连接中断：${String((reason as Error).message ?? reason)}` }));
    } finally {
      patch((turn) => ({ ...turn, running: false }));
      setRunning(false);
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
          <button className="rail-item on">本次对话</button>
          <button
            className="rail-item"
            onClick={() => {
              setTurns([]);
              setThread(crypto.randomUUID());
            }}
          >
            ＋ 新对话
          </button>
          <div className="linkish" style={{ padding: "4px 8px" }} title="历史对话列表需要 GET /sessions">
            历史对话待接口
          </div>
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
          {turns.length === 0 && (
            <div className="welcome">
              <h2>今天想记点什么？</h2>
              <p>可以说「午饭 38，微信」，也可以问「这个月餐饮花了多少」。</p>
            </div>
          )}
          {turns.map((turn, index) => (
            <article className="turn" key={index}>
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
                    onEdited={(updated) => setTurns((items) => items.map((item, turnIndex) =>
                      turnIndex === index ? { ...item, receipts: item.receipts.map((old, slot) => slot === position ? updated : old) } : item
                    ))}
                  />
                ))}
                {turn.ask && (
                  <div className="card warn">
                    <div className="body">
                      <div className="prose">{turn.ask.question}</div>
                      <div className="suggest">
                        {turn.ask.candidates.map((candidate) => (
                          <button key={candidate} onClick={() => send(candidate)}>
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
          <div className="suggest">
            {SUGGESTIONS.map((item) => (
              <button key={item} onClick={() => send(item)} disabled={running}>
                {item}
              </button>
            ))}
          </div>
          <div className="inputbox">
            <textarea
              ref={box}
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
            <button className="btn primary" onClick={() => send()} disabled={running || !text.trim()}>
              {running ? "运行中…" : "发送"}
            </button>
            <kbd>⌘↵</kbd>
          </div>
        </div>
      </section>

      <LedgerPanel receipt={lastWrite} data={data} file={lastWrite?.file ?? "ledger/"} />
    </div>
  );
}
