import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

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
