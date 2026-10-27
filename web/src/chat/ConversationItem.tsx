import { useEffect, useRef, useState } from "react";
import { renameSession, type Session } from "../api";

/** 对话行只管理菜单和原地编辑；删除与切换交给 Chat 统一处理。 */
export function ConversationItem({ item, active, running, onOpen, onRenamed, onDelete }: {
  item: Session;
  active: boolean;
  running: boolean;
  onOpen: () => void;
  onRenamed: (title: string) => void;
  onDelete: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const row = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const disabled = busy || (active && running);

  useEffect(() => {
    if (!editing) return;
    input.current?.focus();
    input.current?.select();
  }, [editing]);

  useEffect(() => {
    if (disabled) { setOpen(false); setEditing(false); }
  }, [disabled]);

  useEffect(() => {
    if (!open) return;
    const outside = (event: MouseEvent) => {
      if (!row.current?.contains(event.target as Node)) setOpen(false);
    };
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setOpen(false); trigger.current?.focus(); return; }
      if (event.ctrlKey || event.metaKey || event.altKey || event.isComposing) return;
      const key = event.key.toUpperCase();
      if (key === "R") { event.preventDefault(); startRename(); }
      if (key === "D") { event.preventDefault(); void remove(); }
    };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", keydown);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", keydown);
    };
  }, [open]);

  function startRename() {
    setDraft(item.title);
    setEditing(true);
    setOpen(false);
    setError("");
  }

  async function save() {
    setEditing(false);
    setBusy(true);
    setError("");
    try {
      const result = await renameSession(item.thread_id, draft);
      onRenamed(result.title);
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }

  async function remove() {
    setOpen(false);
    setBusy(true);
    setError("");
    try { await onDelete(); }
    catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }

  return (
    <div className={`conversation-item${active ? " active" : ""}`} ref={row}>
      <div className="conversation-row">
        {editing ? (
          <input
            ref={input}
            className="conversation-title"
            aria-label="对话标题"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={() => setEditing(false)}
            onKeyDown={(event) => {
              if (event.nativeEvent.isComposing) return;
              if (event.key === "Enter") { event.preventDefault(); void save(); }
              if (event.key === "Escape") { setEditing(false); trigger.current?.focus(); }
            }}
          />
        ) : (
          <button className={`rail-item${active ? " on" : ""}`} title={item.title} disabled={running || busy} onClick={onOpen}>
            {item.title}{item.has_pending_ask ? " · 待答复" : ""}
          </button>
        )}
        {!editing && (
          <button
            ref={trigger}
            className="conversation-more"
            aria-label={`对话「${item.title}」的菜单`}
            aria-expanded={open}
            aria-haspopup="menu"
            disabled={disabled}
            onClick={() => { setOpen(!open); setError(""); }}
          >⋯</button>
        )}
      </div>
      {open && (
        <div className="menu conversation-menu" role="menu" aria-label="对话操作">
          <button role="menuitem" aria-keyshortcuts="R" onClick={startRename}>
            重命名<kbd className="menu-key">R</kbd>
          </button>
          <button role="menuitem" aria-keyshortcuts="D" className="conversation-delete" onClick={() => void remove()}>
            删除<kbd className="menu-key">D</kbd>
          </button>
        </div>
      )}
      {error && <div className="failed conversation-error" role="alert">{error}</div>}
    </div>
  );
}
