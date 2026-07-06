/* Shared primitives: Toggle, Segmented, KPI, Bars, Modal, Drawer, Prog. */

import { type ReactNode } from "react";

export function Toggle({
  on,
  onChange,
  lg,
}: {
  on: boolean;
  onChange: (v: boolean) => void;
  lg?: boolean;
}) {
  return (
    <button
      type="button"
      className={`toggle${on ? " on" : ""}${lg ? " lg" : ""}`}
      onClick={() => onChange(!on)}
      aria-pressed={on}
    />
  );
}

export function Seg<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { id: T; label: string; count?: number }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="seg">
      {options.map((o) => (
        <button key={o.id} className={value === o.id ? "on" : ""} onClick={() => onChange(o.id)}>
          {o.label}
          {o.count !== undefined && <span className="cnt">{o.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Kpi({
  label,
  value,
  note,
  outlined,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  outlined?: boolean;
}) {
  return (
    <div className={`kpi${outlined ? " outlined" : ""}`}>
      <div className="caps">{label}</div>
      <div className="val">{value}</div>
      {note && <div className="note">{note}</div>}
    </div>
  );
}

export function Bars({
  data,
  tips,
}: {
  data: number[];
  tips?: string[];
}) {
  const max = Math.max(1, ...data);
  return (
    <div className="bars">
      {data.map((v, i) => (
        <div
          key={i}
          className={i === data.length - 1 ? "last" : ""}
          style={{ height: `${Math.max(3, (v / max) * 100)}%` }}
        >
          {tips?.[i] && <span className="tip">{tips[i]}</span>}
        </div>
      ))}
    </div>
  );
}

export function Prog({ pct }: { pct: number }) {
  return (
    <div className="prog">
      <i style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
    </div>
  );
}

export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3>{title}</h3>
        {children}
      </div>
    </div>
  );
}

export function Drawer({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <div className="drawer">{children}</div>
    </>
  );
}

export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="grid" style={{ gap: 6 }}>
      <span className="caps">{label}</span>
      {children}
    </label>
  );
}
