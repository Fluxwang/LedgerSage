import "./Modal.css";
import { useEffect, type ReactNode, type RefObject } from "react";

/** 统一确认弹窗的外壳；点蒙版不关闭，内容和按钮交给调用方。 */
export function Modal({ children, onClose, busy = false, initialFocus, labelledBy, className = "" }: {
  children: ReactNode;
  onClose: () => void;
  busy?: boolean;
  initialFocus: RefObject<HTMLElement | null>;
  labelledBy: string;
  className?: string;
}) {
  useEffect(() => { initialFocus.current?.focus(); }, [initialFocus]);

  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      if (!busy) onClose();
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [busy, onClose]);

  return (
    <div className="scrim">
      <div className={`modal ${className}`} role="dialog" aria-modal="true" aria-labelledby={labelledBy} aria-busy={busy}>
        {children}
      </div>
    </div>
  );
}
