/* Screen 20. Акции: monthly percent-off campaigns within a day-of-month window. */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import { Toggle } from "../components/ui";
import { useApp } from "../state/app";

type Sale = {
  id: number;
  title: string;
  discount_pct: number;
  start_day: number;
  end_day: number;
  max_uses: number;
  used_count: number;
  used_period: string;
  enabled: boolean;
};

const EMPTY = { title: "", discount_pct: 20, start_day: 1, end_day: 3, max_uses: 0, enabled: true };

export default function Sales() {
  const { t, toast, confirm } = useApp();
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ["sales"],
    queryFn: () => api.get<{ items: Sale[] }>("/api/admin/sales"),
  });
  const [adding, setAdding] = useState(false);
  const [nw, setNw] = useState({ ...EMPTY });
  const [draft, setDraft] = useState<Record<number, Partial<Sale>>>({});

  const refresh = () => void qc.invalidateQueries({ queryKey: ["sales"] });

  function edit(s: Sale, patch: Partial<Sale>) {
    setDraft((d) => ({ ...d, [s.id]: { ...(d[s.id] ?? {}), ...patch } }));
  }
  function val(s: Sale): Sale {
    return { ...s, ...(draft[s.id] ?? {}) };
  }

  async function add() {
    if (nw.start_day > nw.end_day) {
      toast(t.saleDayOrder);
      return;
    }
    try {
      await api.post("/api/admin/sales", {
        title: nw.title.trim() || undefined,
        discount_pct: nw.discount_pct,
        start_day: nw.start_day,
        end_day: nw.end_day,
        max_uses: nw.max_uses,
        enabled: nw.enabled,
      });
      setAdding(false);
      setNw({ ...EMPTY });
      refresh();
    } catch (e) {
      toast((e as Error).message);
    }
  }

  async function save(s: Sale) {
    const v = val(s);
    if (v.start_day > v.end_day) {
      toast(t.saleDayOrder);
      return;
    }
    try {
      await api.patch(`/api/admin/sales/${s.id}`, {
        title: v.title,
        discount_pct: v.discount_pct,
        start_day: v.start_day,
        end_day: v.end_day,
        max_uses: v.max_uses,
        enabled: v.enabled,
      });
      setDraft((d) => {
        const n = { ...d };
        delete n[s.id];
        return n;
      });
      toast(`${t.saved} ✓`);
      refresh();
    } catch (e) {
      toast((e as Error).message);
    }
  }

  async function remove(s: Sale) {
    if (!(await confirm(t.deleteConfirm))) return;
    try {
      await api.del(`/api/admin/sales/${s.id}`);
      refresh();
    } catch (e) {
      toast((e as Error).message);
    }
  }

  const num = (v: string, lo: number, hi: number) => Math.min(hi, Math.max(lo, Number(v) || lo));
  const items = list.data?.items ?? [];

  function dayFields(o: { start_day: number; end_day: number }, on: (p: Partial<Sale>) => void) {
    return (
      <>
        <label className="row" style={{ gap: 6 }}>
          <span className="caps">{t.saleFrom}</span>
          <input
            className="input num"
            style={{ width: 64 }}
            type="number"
            min={1}
            max={31}
            value={o.start_day}
            onChange={(e) => on({ start_day: num(e.target.value, 1, 31) })}
          />
        </label>
        <label className="row" style={{ gap: 6 }}>
          <span className="caps">{t.saleTo}</span>
          <input
            className="input num"
            style={{ width: 64 }}
            type="number"
            min={1}
            max={31}
            value={o.end_day}
            onChange={(e) => on({ end_day: num(e.target.value, 1, 31) })}
          />
        </label>
      </>
    );
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="h1">{t.salesTitle}</h1>
          <div className="caps sub">{t.salesSub}</div>
        </div>
        <div className="actions">
          <button className="btn primary" onClick={() => setAdding(true)}>
            + {t.saleAdd}
          </button>
        </div>
      </div>

      {adding && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <input
              className="input"
              style={{ flex: 1, minWidth: 160 }}
              placeholder={t.saleTitle}
              value={nw.title}
              onChange={(e) => setNw({ ...nw, title: e.target.value })}
            />
            <label className="row" style={{ gap: 6 }}>
              <span className="caps">%</span>
              <input
                className="input num"
                style={{ width: 70 }}
                type="number"
                min={1}
                max={100}
                value={nw.discount_pct}
                onChange={(e) => setNw({ ...nw, discount_pct: num(e.target.value, 1, 100) })}
              />
            </label>
            {dayFields(nw, (p) => setNw({ ...nw, ...p }))}
            <label className="row" style={{ gap: 6 }}>
              <span className="caps">{t.saleMaxUses}</span>
              <input
                className="input num"
                style={{ width: 80 }}
                type="number"
                min={0}
                value={nw.max_uses}
                onChange={(e) => setNw({ ...nw, max_uses: Math.max(0, Number(e.target.value) || 0) })}
              />
            </label>
          </div>
          <div className="row" style={{ gap: 6, marginTop: 8, justifyContent: "flex-end" }}>
            <button className="btn secondary" onClick={() => setAdding(false)}>
              {t.cancel}
            </button>
            <button className="btn primary" onClick={add}>
              {t.save}
            </button>
          </div>
        </div>
      )}

      <div className="grid" style={{ gap: 12 }}>
        {items.map((s0) => {
          const s = val(s0);
          const dirty = JSON.stringify(s) !== JSON.stringify(s0);
          return (
            <div key={s0.id} className="card">
              <div className="row" style={{ justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                <input
                  className="input"
                  style={{ flex: 1, minWidth: 160 }}
                  value={s.title}
                  onChange={(e) => edit(s0, { title: e.target.value })}
                />
                <span className="cap-pill">−{s.discount_pct}%</span>
                <Toggle on={s.enabled} onChange={(v) => edit(s0, { enabled: v })} />
              </div>
              <div className="row" style={{ gap: 12, marginTop: 10, flexWrap: "wrap", alignItems: "center" }}>
                <label className="row" style={{ gap: 6 }}>
                  <span className="caps">%</span>
                  <input
                    className="input num"
                    style={{ width: 70 }}
                    type="number"
                    min={1}
                    max={100}
                    value={s.discount_pct}
                    onChange={(e) => edit(s0, { discount_pct: num(e.target.value, 1, 100) })}
                  />
                </label>
                {dayFields(s, (p) => edit(s0, p))}
                <label className="row" style={{ gap: 6 }}>
                  <span className="caps">{t.saleMaxUses}</span>
                  <input
                    className="input num"
                    style={{ width: 80 }}
                    type="number"
                    min={0}
                    value={s.max_uses}
                    onChange={(e) => edit(s0, { max_uses: Math.max(0, Number(e.target.value) || 0) })}
                  />
                </label>
                <span className="caps dim">
                  {t.saleUsed}: {s0.used_count}
                  {s0.max_uses > 0 ? ` / ${s0.max_uses}` : ""}
                </span>
                <button className="btn secondary sm" style={{ marginLeft: "auto" }} onClick={() => remove(s0)}>
                  {t.delete}
                </button>
                {dirty && (
                  <button className="btn primary sm" onClick={() => save(s0)}>
                    {t.save}
                  </button>
                )}
              </div>
            </div>
          );
        })}
        {items.length === 0 && <div className="caps dim" style={{ padding: 20, textAlign: "center" }}>{t.salesEmpty}</div>}
      </div>
    </>
  );
}
