/* Screen 19. Партнёры: named referral codes (deep-link suffix) for ad channels. */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import { Toggle } from "../components/ui";
import { useApp } from "../state/app";

type Partner = {
  id: number;
  name: string;
  telegram_id: number | null;
  code: string;
  enabled: boolean;
  created_at: string | null;
};

export default function Partners() {
  const { t, toast, confirm } = useApp();
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ["partners"],
    queryFn: () => api.get<{ items: Partner[] }>("/api/admin/partners"),
  });
  const [adding, setAdding] = useState(false);
  const [nw, setNw] = useState({ name: "", code: "", telegram_id: "" });
  const [draft, setDraft] = useState<Record<number, Partial<Partner>>>({});

  const refresh = () => void qc.invalidateQueries({ queryKey: ["partners"] });

  function edit(p: Partner, patch: Partial<Partner>) {
    setDraft((d) => ({ ...d, [p.id]: { ...(d[p.id] ?? {}), ...patch } }));
  }
  function val(p: Partner): Partner {
    return { ...p, ...(draft[p.id] ?? {}) };
  }

  async function add() {
    if (!nw.name.trim()) return;
    const body: Record<string, unknown> = { name: nw.name.trim() };
    if (nw.code.trim()) body.code = nw.code.trim();
    if (nw.telegram_id.trim()) body.telegram_id = Number(nw.telegram_id.trim()) || null;
    try {
      await api.post("/api/admin/partners", body);
      setAdding(false);
      setNw({ name: "", code: "", telegram_id: "" });
      refresh();
    } catch (e) {
      toast((e as Error).message);
    }
  }

  async function save(p: Partner) {
    const v = val(p);
    try {
      await api.patch(`/api/admin/partners/${p.id}`, {
        name: v.name,
        telegram_id: v.telegram_id,
        enabled: v.enabled,
      });
      setDraft((d) => {
        const n = { ...d };
        delete n[p.id];
        return n;
      });
      toast(`${t.saved} ✓`);
      refresh();
    } catch (e) {
      toast((e as Error).message);
    }
  }

  async function remove(p: Partner) {
    if (!(await confirm(t.deleteConfirm))) return;
    try {
      await api.del(`/api/admin/partners/${p.id}`);
      refresh();
    } catch (e) {
      toast((e as Error).message);
    }
  }

  const items = list.data?.items ?? [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="h1">{t.partners}</h1>
          <div className="caps sub">{t.partnersSub}</div>
        </div>
        <div className="actions">
          <button className="btn primary" onClick={() => setAdding(true)}>
            + {t.partnerAdd}
          </button>
        </div>
      </div>

      {adding && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            <input
              className="input"
              style={{ flex: 1, minWidth: 160 }}
              placeholder={t.partnerName}
              value={nw.name}
              onChange={(e) => setNw({ ...nw, name: e.target.value })}
            />
            <input
              className="input mono"
              style={{ width: 150 }}
              placeholder={t.partnerCode}
              value={nw.code}
              onChange={(e) => setNw({ ...nw, code: e.target.value })}
            />
            <input
              className="input num"
              style={{ width: 150 }}
              placeholder="Telegram ID"
              value={nw.telegram_id}
              onChange={(e) => setNw({ ...nw, telegram_id: e.target.value })}
            />
          </div>
          <div className="caps dim" style={{ marginTop: 6 }}>
            {t.partnerCodeHint}
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
        {items.map((p0) => {
          const p = val(p0);
          const dirty = JSON.stringify(p) !== JSON.stringify(p0);
          return (
            <div key={p0.id} className="card">
              <div className="row" style={{ justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                <input
                  className="input"
                  style={{ flex: 1, minWidth: 160 }}
                  value={p.name}
                  onChange={(e) => edit(p0, { name: e.target.value })}
                />
                <span className="cap-pill mono">?start={p.code}</span>
                <Toggle on={p.enabled} onChange={(v) => edit(p0, { enabled: v })} />
              </div>
              <div className="row" style={{ gap: 10, marginTop: 8, flexWrap: "wrap" }}>
                <input
                  className="input num"
                  style={{ width: 170 }}
                  placeholder="Telegram ID"
                  value={p.telegram_id ?? ""}
                  onChange={(e) =>
                    edit(p0, { telegram_id: e.target.value.trim() ? Number(e.target.value) || null : null })
                  }
                />
                <button className="btn secondary sm" style={{ marginLeft: "auto" }} onClick={() => remove(p0)}>
                  {t.delete}
                </button>
                {dirty && (
                  <button className="btn primary sm" onClick={() => save(p0)}>
                    {t.save}
                  </button>
                )}
              </div>
            </div>
          );
        })}
        {items.length === 0 && <div className="caps dim" style={{ padding: 20, textAlign: "center" }}>{t.partnersEmpty}</div>}
      </div>
    </>
  );
}
