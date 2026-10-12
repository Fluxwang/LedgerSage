import { useEffect, useRef, useState } from "react";

export function UserMenu({ username, onExplore, onLogout }: { username: string; onExplore: () => void; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  return (
    <div className="usermenu" ref={box}>
      <button onClick={() => setOpen(!open)}>
        <span className="avatar">{username.slice(0, 1).toUpperCase() || "?"}</span>
        <span style={{ fontSize: 12.5 }}>{username}</span>
        <span style={{ fontSize: 10, color: "var(--ink-3)" }}>{open ? "▴" : "▾"}</span>
      </button>
      {open && (
        <div className="menu">
          <button disabled title="设置页不在当前范围" style={{ opacity: 0.45, cursor: "not-allowed" }}>
            设置
          </button>
          <button onClick={() => { setOpen(false); onExplore(); }}>统计页面</button>
          <button onClick={onLogout}>退出登录</button>
        </div>
      )}
    </div>
  );
}
