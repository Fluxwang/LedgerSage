import { useMemo, useState } from "react";
import type { Dashboard } from "../api";
import { abs } from "../ui";

type Node = { account: string; label: string; depth: number; amount: number };

/** 用 dashboard 已有的余额和分类合计拼一棵树；Income 缺聚合，所以不在树里。 */
function buildTree(data: Dashboard): Node[] {
  const nodes: Node[] = [];
  const push = (rows: { account: string; amount: number }[], root: string) => {
    if (rows.length === 0) return;
    nodes.push({
      account: root,
      label: root,
      depth: 0,
      amount: rows.reduce((sum, row) => sum + row.amount, 0),
    });
    for (const row of rows.sort(
      (a, b) => Math.abs(b.amount) - Math.abs(a.amount),
    ))
      nodes.push({
        account: row.account,
        label: row.account.slice(root.length + 1),
        depth: 1,
        amount: row.amount,
      });
  };
  push(
    data.accounts
      .filter((card) => card.kind === "asset")
      .map((card) => ({ account: card.account, amount: Number(card.balance) })),
    "Assets",
  );
  push(
    data.accounts
      .filter((card) => card.kind === "liability")
      .map((card) => ({ account: card.account, amount: Number(card.balance) })),
    "Liabilities",
  );
  push(
    data.categories.map((item) => ({
      account: item.account,
      amount: Number(item.amount),
    })),
    "Expenses",
  );
  return nodes;
}

export function Tree({
  data,
  onPick,
  picked,
}: {
  data: Dashboard;
  onPick: (prefix: string) => void;
  picked: string;
}) {
  const nodes = useMemo(() => buildTree(data), [data]);
  /** 记录每个一级账户是否展开；默认全部收起，只显示 Assets / Liabilities / Expenses。 */
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const toggle = (root: string) =>
    setOpen((prev) => ({ ...prev, [root]: !prev[root] }));
  return (
    <div className="tree">
      {nodes.map((node) => {
        const root = node.account.split(":")[0];
        if (node.depth > 0 && !open[root]) return null;
        return (
          <button
            key={node.account}
            className={`lv${node.depth + 1}${picked === node.account ? " on" : ""}`}
            onClick={() => onPick(node.account)}
            title={node.account}
          >
            {node.depth === 0 && (
              <span
                className={`caret${open[root] ? " on" : ""}`}
                role="button"
                aria-label={open[root] ? `收起 ${root}` : `展开 ${root}`}
                onClick={(event) => {
                  event.stopPropagation();
                  toggle(root);
                }}
              >
                ▸
              </span>
            )}
            <span className="label">{node.label}</span>
            <span className="amt">
              {node.amount < 0 ? "−" : ""}
              {abs(node.amount, 0)}
            </span>
          </button>
        );
      })}
    </div>
  );
}
