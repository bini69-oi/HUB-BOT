/* Screen 06 — Кастомизация Miniapp: 8 templates + branding + phone preview. */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import { Field } from "../components/ui";
import { useApp } from "../state/app";

type Config = {
  template: string;
  title: string | null;
  greeting: string | null;
  accent_color: string | null;
  photo_scale_pct: number;
  published_at: string | null;
  templates: string[];
};

const SWATCHES = ["#2E63E7", "#31A24C", "#7C5CFF", "#EF7048", "#C03B2D", "#0C8F4E", "#111111"];

const TEMPLATE_NAMES: Record<string, string> = {
  minimal: "Минимал",
  private: "Прайват",
  buddy: "Бадди",
  native: "Нативный",
  terminal: "Терминал",
  magazine: "Журнал",
  neon: "Неон",
  pop: "Поп",
};

/* Tiny layout sketches per template (mini-scheme cards from the design). */
function Sketch({ id }: { id: string }) {
  const bar = (w: string, h = 5) => (
    <div style={{ width: w, height: h, background: "var(--border2)", borderRadius: 2 }} />
  );
  switch (id) {
    case "minimal":
    case "native":
      return (
        <div className="grid" style={{ gap: 3 }}>
          {bar("70%")} {bar("100%", 14)} {bar("100%", 8)} {bar("100%", 8)}
        </div>
      );
    case "private":
    case "magazine":
      return (
        <div className="grid" style={{ gap: 3 }}>
          {bar("50%", 8)} {bar("100%", 18)} {bar("80%")} {bar("60%")}
        </div>
      );
    case "buddy":
    case "pop":
      return (
        <div className="grid" style={{ gap: 3 }}>
          <div className="row" style={{ gap: 3 }}>
            {bar("48%", 16)} {bar("48%", 16)}
          </div>
          {bar("100%", 12)} {bar("70%")}
        </div>
      );
    case "terminal":
      return (
        <div className="grid" style={{ gap: 2 }}>
          {bar("90%", 4)} {bar("75%", 4)} {bar("85%", 4)} {bar("60%", 4)} {bar("80%", 4)}
        </div>
      );
    case "neon":
      return (
        <div className="grid" style={{ gap: 3 }}>
          <div
            style={{
              width: 26,
              height: 26,
              borderRadius: "50%",
              border: "3px solid var(--border2)",
              margin: "0 auto",
            }}
          />
          {bar("100%", 8)} {bar("100%", 8)}
        </div>
      );
    default:
      return null;
  }
}

export default function Miniapp() {
  const { t, toast } = useApp();
  const qc = useQueryClient();
  const [cfg, setCfg] = useState<Config | null>(null);
  const [dirty, setDirty] = useState(false);

  const data = useQuery({
    queryKey: ["miniapp"],
    queryFn: () => api.get<Config>("/api/admin/miniapp"),
  });

  useEffect(() => {
    if (data.data && !dirty) setCfg(data.data);
  }, [data.data, dirty]);

  function patch(p: Partial<Config>) {
    setCfg((c) => (c ? { ...c, ...p } : c));
    setDirty(true);
  }

  async function save(publish = false) {
    if (!cfg) return;
    try {
      await api.patch("/api/admin/miniapp", {
        template: cfg.template,
        title: cfg.title,
        greeting: cfg.greeting,
        accent_color: cfg.accent_color,
        photo_scale_pct: cfg.photo_scale_pct,
      });
      if (publish) await api.post("/api/admin/miniapp/publish");
      setDirty(false);
      void qc.invalidateQueries({ queryKey: ["miniapp"] });
      toast(publish ? t.published : t.saved);
    } catch (e) {
      toast(`${t.error}: ${(e as Error).message}`);
    }
  }

  const accent = cfg?.accent_color ?? "#2E63E7";
  // Black CTA text when the accent is light (per design note).
  const light = (() => {
    const hex = accent.replace("#", "");
    const r = parseInt(hex.slice(0, 2), 16);
    const g = parseInt(hex.slice(2, 4), 16);
    const b = parseInt(hex.slice(4, 6), 16);
    return r * 0.299 + g * 0.587 + b * 0.114 > 160;
  })();

  return (
    <>
      <div className="page-head">
        <h1 className="h1">{t.miniapp}</h1>
        <div className="actions">
          <button className="btn primary" onClick={() => void save(true)}>
            {t.publish}
          </button>
        </div>
      </div>

      {/* template cards */}
      <div
        className="kpis"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))", marginBottom: 20 }}
      >
        {(cfg?.templates ?? []).map((id) => (
          <button
            key={id}
            onClick={() => patch({ template: id })}
            style={{
              background: "var(--panel)",
              border: cfg?.template === id ? "2px solid var(--text)" : "1px solid var(--border)",
              borderRadius: 4,
              padding: 12,
              cursor: "pointer",
              textAlign: "left",
              color: "var(--text)",
            }}
          >
            <Sketch id={id} />
            <div style={{ fontSize: 12.5, marginTop: 8, fontWeight: 500 }}>
              {TEMPLATE_NAMES[id] ?? id}
            </div>
            <div className="mono dim" style={{ fontSize: 9.5 }}>
              {id}
            </div>
          </button>
        ))}
      </div>

      <div className="cols">
        {/* settings */}
        <div className="card main-col" style={{ maxWidth: 520 }}>
          {cfg && (
            <div className="grid" style={{ gap: 14 }}>
              <Field label={t.appTitle}>
                <input
                  className="input"
                  value={cfg.title ?? ""}
                  placeholder="My VPN"
                  onChange={(e) => patch({ title: e.target.value })}
                />
              </Field>
              <Field label={t.greeting}>
                <input
                  className="input"
                  value={cfg.greeting ?? ""}
                  placeholder="Привет! Твоя защита активна"
                  onChange={(e) => patch({ greeting: e.target.value })}
                />
              </Field>
              <Field label={t.accent}>
                <div className="row" style={{ flexWrap: "wrap" }}>
                  {SWATCHES.map((c) => (
                    <button
                      key={c}
                      onClick={() => patch({ accent_color: c })}
                      style={{
                        width: 24,
                        height: 24,
                        borderRadius: 3,
                        cursor: "pointer",
                        background: c,
                        border:
                          accent === c ? "2px solid var(--text)" : "1px solid var(--border2)",
                      }}
                    />
                  ))}
                  <input
                    className="input mono"
                    style={{ width: 100 }}
                    value={cfg.accent_color ?? ""}
                    placeholder="#HEX"
                    onChange={(e) => patch({ accent_color: e.target.value || null })}
                  />
                </div>
              </Field>
              <Field label={`${t.photoScale} · ${cfg.photo_scale_pct}%`}>
                <input
                  type="range"
                  min={70}
                  max={130}
                  value={cfg.photo_scale_pct}
                  onChange={(e) => patch({ photo_scale_pct: Number(e.target.value) })}
                />
              </Field>
              {dirty && (
                <button className="btn primary" onClick={() => void save(false)}>
                  {t.save}
                </button>
              )}
            </div>
          )}
        </div>

        {/* phone preview */}
        <div className="side-col" style={{ alignItems: "center" }}>
          <div
            style={{
              width: 280,
              border: "1px solid var(--border2)",
              borderRadius: 24,
              padding: 10,
              background: "var(--panel)",
              margin: "0 auto",
            }}
          >
            <div
              style={{
                borderRadius: 16,
                overflow: "hidden",
                background: "var(--panel2)",
                border: "1px solid var(--border)",
              }}
            >
              {/* cover */}
              <div
                style={{
                  height: Math.round(80 * ((cfg?.photo_scale_pct ?? 100) / 100)),
                  background: `repeating-linear-gradient(45deg, ${accent}22, ${accent}22 8px, var(--panel2) 8px, var(--panel2) 16px)`,
                  display: "grid",
                  placeItems: "center",
                }}
              >
                <b style={{ fontSize: 14 }}>{cfg?.title || "My VPN"}</b>
              </div>
              <div style={{ padding: 14 }}>
                <div className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
                  {cfg?.greeting || "Привет! Твоя защита активна"}
                </div>
                {/* template-specific body */}
                {cfg?.template === "terminal" ? (
                  <div className="mono" style={{ fontSize: 10.5, lineHeight: 1.8 }}>
                    <div>01 status · active</div>
                    <div>02 days_left · 23d</div>
                    <div>03 devices · 2/5</div>
                    <div>04 traffic · 41.2gb</div>
                  </div>
                ) : cfg?.template === "neon" ? (
                  <div style={{ textAlign: "center" }}>
                    <div
                      style={{
                        width: 74,
                        height: 74,
                        margin: "6px auto 8px",
                        borderRadius: "50%",
                        border: `5px solid ${accent}`,
                        display: "grid",
                        placeItems: "center",
                        fontSize: 20,
                        fontWeight: 700,
                      }}
                    >
                      23
                    </div>
                    <div className="dim" style={{ fontSize: 11 }}>
                      дня защиты
                    </div>
                  </div>
                ) : (
                  <div className="grid" style={{ gap: 6 }}>
                    <div
                      style={{
                        background: "var(--panel)",
                        border: "1px solid var(--border)",
                        borderRadius: 8,
                        padding: 10,
                        fontSize: 12,
                      }}
                    >
                      <div className="row" style={{ justifyContent: "space-between" }}>
                        <span className="muted">Подписка</span>
                        <b>23 дня</b>
                      </div>
                    </div>
                    <div
                      style={{
                        background: "var(--panel)",
                        border: "1px solid var(--border)",
                        borderRadius: 8,
                        padding: 10,
                        fontSize: 12,
                      }}
                    >
                      <div className="row" style={{ justifyContent: "space-between" }}>
                        <span className="muted">Устройства</span>
                        <b>2 из 5</b>
                      </div>
                    </div>
                  </div>
                )}
                {/* CTA */}
                <div
                  style={{
                    marginTop: 12,
                    background: accent,
                    color: light ? "#111" : "#fff",
                    borderRadius: 8,
                    textAlign: "center",
                    padding: "10px 0",
                    fontSize: 13,
                    fontWeight: 600,
                  }}
                >
                  Продлить
                </div>
              </div>
            </div>
          </div>
          <div className="caps" style={{ textAlign: "center" }}>
            {t.preview} · {TEMPLATE_NAMES[cfg?.template ?? ""] ?? cfg?.template}
          </div>
        </div>
      </div>
    </>
  );
}
