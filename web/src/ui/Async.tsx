import React, { useCallback, useEffect, useState } from "react";
import { MissingEndpoint } from "../api";

export type AsyncState<T> = { data?: T; error?: unknown; loading: boolean };

/** 把「接口还没有」和「接口报错」分开：前者渲染占位卡，后者渲染错误条。 */
export function useAsync<T>(load: () => Promise<T>, deps: unknown[]): AsyncState<T> & { reload: () => void } {
  const [state, setState] = useState<AsyncState<T>>({ loading: true });
  const [nonce, setNonce] = useState(0);
  const reload = useCallback(() => setNonce((value) => value + 1), []);
  useEffect(() => {
    let live = true;
    setState({ loading: true });
    Promise.resolve()
      .then(load)
      .then((data) => live && setState({ data, loading: false }))
      .catch((error) => live && setState({ error, loading: false }));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);
  return { ...state, reload };
}

export function Stub({ endpoint, why }: { endpoint: string; why: string }) {
  return (
    <div className="stub">
      <b>这块还等后端</b>
      <code>{endpoint}</code>
      <small>{why}</small>
    </div>
  );
}

/** 统一的加载 / 缺接口 / 报错三态。data 就绪时才调用 children。 */
export function Async<T>({
  state,
  children,
  empty,
}: {
  state: AsyncState<T>;
  children: (data: T) => React.ReactNode;
  empty?: React.ReactNode;
}) {
  if (state.loading) return <div className="loading">读取账本…</div>;
  if (state.error instanceof MissingEndpoint)
    return <Stub endpoint={state.error.endpoint} why={state.error.why} />;
  if (state.error) return <div className="failed">{String((state.error as Error).message ?? state.error)}</div>;
  if (state.data === undefined) return <>{empty ?? <div className="hollow">没有数据</div>}</>;
  return <>{children(state.data)}</>;
}
