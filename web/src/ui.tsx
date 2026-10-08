import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { MissingEndpoint } from "./api";

/* ---------------------------------------------------------------- 数字与日期 */

export const num = (value: string | number, digits = 0) => {
  const parsed = typeof value === "number" ? value : Number(String(value).replace(/,/g, ""));
  if (!Number.isFinite(parsed)) return String(value);
  return parsed.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
};

/** 金额在账本里带符号，展示时支出取绝对值，方向交给颜色和文案。 */
export const abs = (value: string | number, digits = 0) => num(Math.abs(Number(String(value).replace(/,/g, "")) || 0), digits);

export const pct = (part: number, whole: number) => (whole ? Math.min(100, (part / whole) * 100) : 0);

export const monthLabel = (iso: string) => `${iso.slice(5, 7)} 月`;

export const today = () => new Date().toISOString().slice(0, 10);

export function monthsBack(count: number): string {
  const now = new Date();
  now.setDate(1);
  now.setMonth(now.getMonth() - (count - 1));
  return now.toISOString().slice(0, 7);
}

/* -------------------------------------------------------------------- 折叠 */

export function Disclose({
  label,
  children,
  defaultOpen = false,
  bare = false,
}: {
  label: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  bare?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (bare)
    return (
      <>
        <button className="linkish" onClick={() => setOpen(!open)}>
          {open ? "▾" : "▸"} {label}
        </button>
        {open && children}
      </>
    );
  return (
    <>
      <button className="disclose" onClick={() => setOpen(!open)}>
        <span className="caret">{open ? "▾" : "▸"}</span>
        <span className="label">{label}</span>
      </button>
      {open && children}
    </>
  );
}

/* -------------------------------------------------------------- 异步与占位 */

type AsyncState<T> = { data?: T; error?: unknown; loading: boolean };

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

/* -------------------------------------------------------------------- 图元 */

export function Bar({ label, value, share, peak }: { label: string; value: string; share: number; peak?: boolean }) {
  return (
    <div className={`barrow${peak ? " peak" : ""}`}>
      <div className="lbl">{label}</div>
      <div className="track">
        <i style={{ width: `${Math.max(0, Math.min(100, share))}%` }} />
      </div>
      <div className="val">{value}</div>
    </div>
  );
}

export function Meter({ used, limit }: { used: number; limit: number }) {
  const ratio = limit ? used / limit : 0;
  const state = ratio >= 1 ? "exceeded" : ratio >= 0.75 ? "at-risk" : "ok";
  return (
    <div className={`meter ${state}`}>
      <i style={{ width: `${Math.min(100, ratio * 100)}%` }} />
    </div>
  );
}

export const budgetState = (used: number, limit: number) =>
  limit && used >= limit ? "exceeded" : limit && used / limit >= 0.75 ? "at-risk" : "ok";

export const BUDGET_LABEL: Record<string, string> = { exceeded: "已超支", "at-risk": "即将超支", ok: "健康" };

/* -------------------------------------------------------------------- 下拉 */

export type PickOption = { value: string; label: string };

const POP_MAX = 268;

/**
 * 账户选择器。原生 select 的弹层由系统绘制，和暖纸底的设计对不上，
 * 所以自己画一个：触发器像输入框，弹层复用用户菜单那套纸面 + 阴影。
 */
export function Picker({
  value,
  options,
  onChange,
  disabled,
  label,
  bare = false,
}: {
  value: string;
  options: PickOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  label: string;
  bare?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [box, setBox] = useState<{ left: number; top: number; width: number } | null>(null);
  const anchor = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const selected = options.findIndex((option) => option.value === value);
  const current = selected >= 0 ? options[selected].label : value;

  const place = useCallback(() => {
    const rect = anchor.current?.getBoundingClientRect();
    if (!rect) return;
    const wanted = Math.min(POP_MAX, options.length * 32 + 12);
    const below = window.innerHeight - rect.bottom - 10;
    // 下方放不下、而上方更宽裕时翻到触发器上面，别让弹层被窗口底边切掉。
    const drop = below >= wanted || below >= rect.top - 10;
    setBox({
      left: rect.left,
      top: drop ? rect.bottom + 5 : Math.max(8, rect.top - 5 - Math.min(wanted, rect.top - 18)),
      width: rect.width,
    });
  }, [options.length]);

  useLayoutEffect(() => {
    if (!open) return;
    place();
    setActive(selected >= 0 ? selected : 0);
    pop.current?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // 弹层用 fixed 定位躲开卡片的 overflow:hidden，外层一滚就得跟着关掉。
  useEffect(() => {
    if (!open) return;
    // 弹层自己滚动不算「外层滚走了」。
    const close = (event: Event) => {
      if (event.target instanceof Node && pop.current?.contains(event.target)) return;
      setOpen(false);
    };
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    pop.current?.querySelector<HTMLElement>(".active")?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  function pick(index: number) {
    const option = options[index];
    setOpen(false);
    anchor.current?.focus();
    if (option && option.value !== value) onChange(option.value);
  }

  function onKey(event: React.KeyboardEvent) {
    const keys: Record<string, number> = {
      ArrowDown: Math.min(options.length - 1, active + 1),
      ArrowUp: Math.max(0, active - 1),
      Home: 0,
      End: options.length - 1,
    };
    if (event.key in keys) {
      event.preventDefault();
      setActive(keys[event.key]);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      pick(active);
    } else if (event.key === "Escape" || event.key === "Tab") {
      setOpen(false);
      anchor.current?.focus();
    }
  }

  return (
    <>
      <button
        ref={anchor}
        type="button"
        role="combobox"
        aria-label={label}
        aria-expanded={open}
        aria-haspopup="listbox"
        disabled={disabled}
        className={`picker${bare ? " bare" : ""}${open ? " on" : ""}`}
        onClick={() => setOpen(!open)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span>{current || "—"}</span>
        <Chevron />
      </button>
      {open &&
        box &&
        createPortal(
          <>
            <div className="picker-veil" onMouseDown={() => setOpen(false)} />
            <div
              ref={pop}
              role="listbox"
              aria-label={label}
              tabIndex={-1}
              className="picker-pop"
              onKeyDown={onKey}
              style={{ left: box.left, top: box.top, minWidth: box.width }}
            >
              {options.map((option, index) => (
                <button
                  key={option.value}
                  type="button"
                  role="option"
                  aria-selected={index === selected}
                  className={`${index === active ? "active" : ""}${index === selected ? " sel" : ""}`}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => pick(index)}
                >
                  <i className="tick">{index === selected ? "✓" : ""}</i>
                  <span>{option.label}</span>
                </button>
              ))}
            </div>
          </>,
          document.body,
        )}
    </>
  );
}

const Chevron = () => (
  <svg className="chev" width="9" height="6" viewBox="0 0 9 6" aria-hidden="true">
    <path d="M1 1.2 4.5 4.7 8 1.2" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);
