import { useState } from "react";
import { runs } from "../api";
import { ToolTrace, type Step } from "../chat/ToolTrace";
import { Async, useAsync } from "../ui";

const NODES: Record<string, string> = {
  CLASSIFY: "classify", PARSE: "extract", TOOL: "tools", ASK: "prepare_ask", REPLY: "reply",
};

function RunDetail({ id }: { id: string }) {
  const detail = useAsync(() => runs.detail(id), [id]);
  return (
    <Async state={detail}>
      {(run) => (
        <article className="run-detail">
          <div className="kicker">用户原话</div>
          <blockquote>{run.message || run.title}</blockquote>
          <h2>{run.title}</h2>
          <p className="muted">{run.created_at} · {run.status}</p>
          <ToolTrace running={false} steps={run.steps.map((step: Omit<Step, "node">) => ({
            ...step,
            node: step.payload?.receipt?.tool ? "query" : NODES[step.kicker ?? ""] ?? "step",
          }))} />
        </article>
      )}
    </Async>
  );
}

/** 决策历史按运行查看，与会话回放分别使用各自的接口。 */
export function RunHistory() {
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string>();
  const history = useAsync(() => runs.list(`page=${page}&size=20`), [page]);
  return (
    <main className="run-history">
      <aside>
        <h2>决策历史</h2>
        <Async state={history}>
          {({ rows, total }) => (
            <>
              {rows.length === 0 && <div className="hollow">还没有运行记录</div>}
              {rows.map((run) => (
                <button key={run.id} className={`rail-item${selected === run.id ? " on" : ""}`}
                  onClick={() => setSelected(run.id)}>
                  {run.title}
                </button>
              ))}
              <div className="history-pages">
                <button className="btn sm" disabled={page === 1} onClick={() => setPage(page - 1)}>上一页</button>
                <span>{page}</span>
                <button className="btn sm" disabled={page * 20 >= total} onClick={() => setPage(page + 1)}>下一页</button>
              </div>
            </>
          )}
        </Async>
      </aside>
      <section>{selected ? <RunDetail key={selected} id={selected} /> : <div className="hollow">选择一次运行查看原话和决策轨迹</div>}</section>
    </main>
  );
}
