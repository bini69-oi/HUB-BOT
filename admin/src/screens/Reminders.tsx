/* Screen 17. Напоминания: hour-based ReminderStep ladder before subscription expiry. */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import { Toggle } from "../components/ui";
import { useApp } from "../state/app";

type Step = {
  id: number;
  hours_before: number;
  text: string;
  button_enabled: boolean;
  enabled: boolean;
};

const PLACEHOLDERS = ["hours", "time", "plan"];

export default function Reminders() {
  const { t, toast, confirm } = useApp();
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ["reminders"],
    queryFn: () => api.get<{ items: Step[] }>("/api/admin/reminders"),
  });
  const [draft, setDraft] = useState<Record<number, Step>>({});
  const [adding, setAdding] = useState(false);
  const [nw, setNw] = useState({ hours_before: 6, text: "" });

  function edit(s: Step, patch: Partial<Step>) {
    setDraft((d) => ({ ...d, [s.id]: { ...s, ...(d[s.id] ?? {}), ...patch } }));
  }
  function val(s: Step): Step {
    return { ...s, ...(draft[s.id] ?? {}) };
  }

  const refresh = () => void qc.invalidateQueries({ queryKey: ["reminders"] });

  async function save(s: Step) {
    const v = val(s);
    try {
      await api.patch(`/api/admin/reminders/${s.id}`, {
        hours_before: v.hours_before,
        text: v.text,
        button_enabled: v.button_enabled,
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

  async function remove(s: Step) {
    if (!(await confirm(t.deleteConfirm))) return;
    try {
      await api.del(`/api/admin/reminders/${s.id}`);
      refresh();
    } catch (e) {
      toast((e as Error).message);
    }
  }

  async function add() {
    if (!nw.text.trim()) return;
    try {
      await api.post("/api/admin/reminders", {
        hours_before: nw.hours_before,
        text: nw.text,
        button_enabled: true,
        enabled: true,
      });
      setAdding(false);
      setNw({ hours_before: 6, text: "" });
      refresh();
    } catch (e) {
      toast((e as Error).message);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="h1">{t.reminders}</h1>
          <div className="caps sub">{t.remindersSub}</div>
        </div>
        <div className="actions">
          <button className="btn primary" onClick={() => setAdding(true)}>
            + {t.reminderAdd}
          </button>
        </div>
      </div>

      {adding && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="row" style={{ gap: 10, marginBottom: 8 }}>
            <label className="caps">{t.hoursBefore}</label>
            <input
              className="input num"
              style={{ width: 90 }}
              type="number"
              min={0}
              max={8760}
              value={nw.hours_before}
              onChange={(e) => setNw({ ...nw, hours_before: Number(e.target.value) || 0 })}
            />
          </div>
          <textarea
            className="input"
            rows={2}
            placeholder={t.reminderText}
            value={nw.text}
            onChange={(e) => setNw({ ...nw, text: e.target.value })}
          />
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
        {(list.data?.items ?? []).map((s0) => {
          const s = val(s0);
          const dirty = JSON.stringify(s) !== JSON.stringify(s0);
          return (
            <div key={s0.id} className="card">
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
                <div className="row" style={{ gap: 8 }}>
                  <input
                    className="input num"
                    style={{ width: 80 }}
                    type="number"
                    min={0}
                    max={8760}
                    value={s.hours_before}
                    onChange={(e) => edit(s0, { hours_before: Number(e.target.value) || 0 })}
                  />
                  <span className="caps">{t.hoursBefore}</span>
                </div>
                <div className="row" style={{ gap: 14 }}>
                  <label className="row" style={{ gap: 6 }}>
                    <span className="caps">{t.renewButton}</span>
                    <Toggle on={s.button_enabled} onChange={(v) => edit(s0, { button_enabled: v })} />
                  </label>
                  <Toggle on={s.enabled} onChange={(v) => edit(s0, { enabled: v })} />
                </div>
              </div>
              <textarea
                className="input"
                rows={2}
                value={s.text}
                onChange={(e) => edit(s0, { text: e.target.value })}
              />
              <div className="row" style={{ flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                {PLACEHOLDERS.map((p) => (
                  <button
                    key={p}
                    className="btn secondary sm mono"
                    onClick={() => edit(s0, { text: `${s.text}{${p}}` })}
                  >
                    {`{${p}}`}
                  </button>
                ))}
                <button
                  className="btn secondary sm"
                  style={{ marginLeft: "auto" }}
                  onClick={() => remove(s0)}
                >
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
      </div>
    </>
  );
}
