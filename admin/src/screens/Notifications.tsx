/* Screen 16. Уведомления: editable lifecycle message templates (purchase, renewal, refund). */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import { Toggle } from "../components/ui";
import { useApp } from "../state/app";

type Note = {
  event: string;
  title: string;
  text: string;
  enabled: boolean;
  placeholders: string[];
};

type Draft = { text: string; enabled: boolean };

export default function Notifications() {
  const { t, toast } = useApp();
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<{ items: Note[] }>("/api/admin/notifications"),
  });
  const [draft, setDraft] = useState<Record<string, Draft>>({});

  useEffect(() => {
    if (!list.data) return;
    const d: Record<string, Draft> = {};
    for (const n of list.data.items) d[n.event] = { text: n.text, enabled: n.enabled };
    setDraft(d);
  }, [list.data]);

  async function save(ev: string) {
    try {
      await api.patch(`/api/admin/notifications/${ev}`, draft[ev]);
      toast(`${t.saved} ✓`);
      void qc.invalidateQueries({ queryKey: ["notifications"] });
    } catch (e) {
      toast((e as Error).message);
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="h1">{t.notifications}</h1>
          <div className="caps sub">{t.notificationsSub}</div>
        </div>
      </div>
      <div className="grid" style={{ gap: 12 }}>
        {(list.data?.items ?? []).map((n) => {
          const d = draft[n.event] ?? { text: n.text, enabled: n.enabled };
          const dirty = d.text !== n.text || d.enabled !== n.enabled;
          return (
            <div key={n.event} className="card">
              <div className="row" style={{ justifyContent: "space-between", marginBottom: 8 }}>
                <b>{n.title}</b>
                <Toggle
                  on={d.enabled}
                  onChange={(v) => setDraft({ ...draft, [n.event]: { ...d, enabled: v } })}
                />
              </div>
              <textarea
                className="input"
                rows={3}
                value={d.text}
                onChange={(e) => setDraft({ ...draft, [n.event]: { ...d, text: e.target.value } })}
              />
              <div className="row" style={{ flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                {n.placeholders.map((p) => (
                  <button
                    key={p}
                    className="btn secondary sm mono"
                    onClick={() =>
                      setDraft({ ...draft, [n.event]: { ...d, text: `${d.text}{${p}}` } })
                    }
                  >
                    {`{${p}}`}
                  </button>
                ))}
                {dirty && (
                  <button
                    className="btn primary sm"
                    style={{ marginLeft: "auto" }}
                    onClick={() => save(n.event)}
                  >
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
