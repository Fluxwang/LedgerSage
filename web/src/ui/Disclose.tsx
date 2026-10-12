import React, { useState } from "react";

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
