import { Disclose } from "../ui";

export type Step = {
  node: string;
  kicker?: string | null;
  title?: string | null;
  duration_ms?: number;
  payload: any;
};

const INTENT: Record<string, string> = {
  record: "记账",
  query: "查询",
  budget: "预算",
  other: "无法判断",
};

/** 时间线那一行的「人话摘要」，只用 payload 里确实有的字段。 */
function note(step: Step): string {
  const payload = step.payload ?? {};
  switch (step.node) {
    case "classify":
      return `识别为${INTENT[payload.intent] ?? payload.intent ?? "未知"}，置信度 ${Number(payload.confidence ?? 0).toFixed(2)}`;
    case "extract": {
      const count = payload.transactions?.length ?? 0;
      const issues: string[] = payload.issue ?? [];
      if (payload.missing?.length) return `抽出 ${count} 笔，还有 ${payload.missing.length} 个账户需要补充`;
      return issues.length ? `抽出 ${count} 笔，待确认：${issues.join("、")}` : `抽出 ${count} 笔，字段齐全`;
    }
    case "bounce":
      return `第 ${payload.bounce_count ?? 1} 次重新判断意图`;
    case "prepare_ask":
      return payload.ask?.question ?? "信息不足，准备追问";
    case "tools":
      return `写入 ${payload.receipt?.entries?.length ?? 0} 条分录 · ${payload.receipt?.file ?? ""}`;
    case "query": {
      const result = payload.receipt?.result ?? payload.query_result;
      const rows = Array.isArray(result) ? `返回 ${result.length} 行` : "返回聚合结果";
      return `${payload.receipt?.tool ?? "query"} · ${rows}`;
    }
    case "budget":
      return payload.ask ? "预算账户或金额不明确" : `写入 ${payload.receipt?.file ?? "budgets.bean"}`;
    case "other":
      return "意图混合或看不懂，转为追问";
    case "reply":
      return payload.title ?? "生成回复";
    default:
      return step.title ?? step.node;
  }
}

/** query 节点本身就带 arguments/result，其余节点只有一个 payload。 */
function inspect(step: Step): { args?: unknown; result?: unknown; single?: unknown } {
  const receipt = step.payload?.receipt;
  if (receipt && "arguments" in receipt) return { args: receipt.arguments, result: receipt.result };
  if (step.node === "tools") return { args: step.payload?.transactions, result: step.payload?.receipt };
  return { single: step.payload };
}

const json = (value: unknown) => JSON.stringify(value, null, 2);

/** reply / bounce 的 payload 没有可审计的东西，不给它们开折叠行。 */
const INSPECTABLE = (step: Step) => !["reply", "bounce"].includes(step.node);

export function ToolTrace({ steps, running }: { steps: Step[]; running: boolean }) {
  if (steps.length === 0) return null;
  return (
    <div className="card">
        <div className="steps">
          {steps.map((step, index) => (
            <div key={index}>
              {index > 0 && <div className="stem" />}
              <div className={`step${running && index === steps.length - 1 ? " running" : ""}`}>
                <i />
                <div className="name">{step.node}</div>
                <div className="note">{note(step)}</div>
                <div className="grow" />
                {step.duration_ms != null && <div className="ms">{(step.duration_ms / 1000).toFixed(1)}s</div>}
              </div>
            </div>
          ))}
          {running && (
            <>
              <div className="stem" />
              <div className="step waiting">
                <i />
                <div className="name">…</div>
                <div className="note">等待下一步</div>
              </div>
            </>
          )}
        </div>
        {steps.filter(INSPECTABLE).map((step, index) => {
          const parts = inspect(step);
          return (
            <Disclose key={index} label={`${step.node} 的参数与返回`}>
              {parts.single !== undefined ? (
                <div className="io" style={{ gridTemplateColumns: "1fr" }}>
                  <div>
                    <div className="kicker">payload</div>
                    <pre>{json(parts.single)}</pre>
                  </div>
                </div>
              ) : (
                <div className="io">
                  <div>
                    <div className="kicker">arguments</div>
                    <pre>{json(parts.args)}</pre>
                  </div>
                  <div>
                    <div className="kicker">result</div>
                    <pre>{json(parts.result)}</pre>
                  </div>
                </div>
              )}
            </Disclose>
          );
      })}
    </div>
  );
}

export const traceSummary = (steps: Step[], running: boolean) => {
  const tools = steps.filter((step) => step.kicker === "TOOL").length;
  const total = steps.reduce((sum, step) => sum + (step.duration_ms ?? 0), 0);
  if (running) return `运行中 · 第 ${steps.length} 步`;
  return `${tools} 个工具调用 · ${(total / 1000).toFixed(1)}s`;
};