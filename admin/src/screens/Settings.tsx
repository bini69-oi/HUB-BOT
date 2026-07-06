/* Screen 13 — Настройки бота: search + grouped params + dirty-save bar. */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api } from "../api/client";
import { Toggle } from "../components/ui";
import { useApp } from "../state/app";

type Param = {
  key: string;
  category: string;
  type: "bool" | "int" | "str" | "secret";
  name: string;
  description: string;
  value: unknown;
  is_overridden: boolean;
};
type Resp = { categories: { id: string; name: string }[]; params: Param[]; total: number };

export default function Settings() {
  const { t, lang, toast } = useApp();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [dirty, setDirty] = useState<Record<string, unknown>>({});

  const data = useQuery({
    queryKey: ["settings", lang],
    queryFn: () => api.get<Resp>(`/api/admin/settings?lang=${lang}`),
  });

  const filtered = useMemo(() => {
    const params = data.data?.params ?? [];
    if (!q.trim()) return params;
    const needle = q.toLowerCase();
    return params.filter(
      (p) =>
        p.key.toLowerCase().includes(needle) ||
        p.name.toLowerCase().includes(needle) ||
        p.description.toLowerCase().includes(needle),
    );
  }, [data.data, q]);

  const grouped = useMemo(() => {
    const cats = data.data?.categories ?? [];
    return cats
      .map((c) => ({ cat: c, params: filtered.filter((p) => p.category === c.id) }))
      .filter((g) => g.params.length > 0);
  }, [data.data, filtered]);

  function valueOf(p: Param): unknown {
    return p.key in dirty ? dirty[p.key] : p.value;
  }
  function setValue(key: string, v: unknown) {
    setDirty((d) => ({ ...d, [key]: v }));
  }

  async function save() {
    try {
      await api.patch("/api/admin/settings", { changes: dirty });
      setDirty({});
      void qc.invalidateQueries({ queryKey: ["settings"] });
      toast(t.applied);
    } catch (e) {
      toast(`${t.error}: ${(e as Error).message}`);
    }
  }

  const dirtyCount = Object.keys(dirty).length;

  return (
    <>
      <div className="page-head">
        <h1 className="h1">{t.settings}</h1>
        <div className="actions">
          {dirtyCount > 0 && (
            <>
              <span className="cap-pill">
                {t.changed}: {dirtyCount}
              </span>
              <button className="btn secondary" onClick={() => setDirty({})}>
                {t.cancel}
              </button>
              <button className="btn primary" onClick={save}>
                {t.saveApply}
              </button>
            </>
          )}
        </div>
      </div>

      <div className="row" style={{ marginBottom: 16 }}>
        <div style={{ position: "relative", flex: 1 }}>
          <span
            className="dim"
            style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)" }}
          >
            ⌕
          </span>
          <input
            className="input"
            style={{ width: "100%", paddingLeft: 30, paddingRight: 30 }}
            placeholder={t.searchParams}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          {q && (
            <button
              className="dim"
              style={{
                position: "absolute",
                right: 8,
                top: "50%",
                transform: "translateY(-50%)",
                background: "none",
                border: 0,
                cursor: "pointer",
                color: "var(--dim)",
              }}
              onClick={() => setQ("")}
            >
              ✕
            </button>
          )}
        </div>
        <span className="caps" style={{ whiteSpace: "nowrap" }}>
          {q
            ? `${t.found} ${filtered.length}`
            : `${data.data?.total ?? "…"} ${t.paramsHot}`}
        </span>
      </div>

      <div className="tbl">
        {grouped.map((g) => (
          <div key={g.cat.id}>
            <div
              className="tr"
              style={{
                background: "var(--panel2)",
                gridTemplateColumns: "1fr auto",
              }}
            >
              <span className="caps">{g.cat.name}</span>
              <span className="caps">{g.params.length}</span>
            </div>
            {g.params.map((p) => {
              const v = valueOf(p);
              const changed = p.key in dirty;
              return (
                <div key={p.key} className="tr" style={{ gridTemplateColumns: "1fr auto" }}>
                  <div style={{ minWidth: 0 }}>
                    <div className="row" style={{ gap: 7 }}>
                      <b style={{ fontSize: 13.5, fontWeight: 500 }}>{p.name}</b>
                      {(changed || p.is_overridden) && (
                        <span
                          title={changed ? t.changed : "override"}
                          style={{
                            width: 6,
                            height: 6,
                            borderRadius: "50%",
                            background: changed ? "var(--text)" : "var(--dim)",
                            flex: "0 0 auto",
                          }}
                        />
                      )}
                    </div>
                    {p.description && (
                      <div className="muted" style={{ fontSize: 12, marginTop: 1 }}>
                        {p.description}
                      </div>
                    )}
                    <div className="mono dim" style={{ fontSize: 10.5, marginTop: 3 }}>
                      {p.key}
                    </div>
                  </div>
                  <div className="row">
                    {p.type === "bool" ? (
                      <Toggle on={Boolean(v)} onChange={(nv) => setValue(p.key, nv)} />
                    ) : (
                      <input
                        className={`input ${p.type === "int" ? "num" : "mono"}`}
                        style={{ width: p.type === "int" ? 110 : 220 }}
                        type={p.type === "secret" ? "password" : "text"}
                        value={String(v ?? "")}
                        onChange={(e) =>
                          setValue(
                            p.key,
                            p.type === "int" ? Number(e.target.value) || 0 : e.target.value,
                          )
                        }
                      />
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>

      <div className="caps" style={{ marginTop: 14, textAlign: "center" }}>
        {t.hotReloadNote}
      </div>
    </>
  );
}
