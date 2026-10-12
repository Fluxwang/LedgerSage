import { useEffect, useState } from "react";
import { vector as vectorApi } from "../api";

export function VectorButton() {
  const [state, setState] = useState<any>();
  useEffect(() => {
    vectorApi.status().then(setState).catch(() => {});
  }, []);
  // 全量重建在后台跑，轮询到结束为止，让用户看得到进度。
  useEffect(() => {
    if (state?.status !== "running") return;
    const timer = setInterval(() => vectorApi.status().then(setState).catch(() => {}), 2000);
    return () => clearInterval(timer);
  }, [state?.status]);
  if (!state?.enabled || !(state.empty || state.status === "running" || state.status === "failed")) return null;
  return (
    <button
      className="btn sm"
      disabled={state.status === "running"}
      onClick={async () => {
        setState({ ...state, status: "running", completed: 0, total: 0 });
        await vectorApi.rebuild();
      }}
    >
      {state.status === "running"
        ? `索引中 ${state.completed}/${state.total || "…"}`
        : state.status === "failed"
          ? "索引失败，重试"
          : "建立历史索引"}
    </button>
  );
}
