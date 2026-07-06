/* Screen 07 — Рассылки: composer + TG preview + history with live progress. */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api, dtTime } from "../api/client";
import { Prog, Seg, Toggle } from "../components/ui";
import { useApp } from "../state/app";

type Audiences = Record<"all" | "active" | "trial" | "expired", number>;
type Broadcast = {
  id: number;
  audience: string;
  media: string;
  text: string;
  status: string;
  total: number;
  sent: number;
  failed: number;
  progress_pct: number;
  created_at: string | null;
};

export default function Broadcasts() {
  const { t, toast, confirm } = useApp();
  const qc = useQueryClient();
  const [audience, setAudience] = useState<"all" | "active" | "trial" | "expired">("all");
  const [media, setMedia] = useState<"text" | "photo" | "video">("text");
  const [text, setText] = useState("");
  const [renewBtn, setRenewBtn] = useState(false);

  const audiences = useQuery({
    queryKey: ["broadcast-audiences"],
    queryFn: () => api.get<Audiences>("/api/admin/broadcasts/audiences"),
  });
  const history = useQuery({
    queryKey: ["broadcasts"],
    queryFn: () => api.get<{ items: Broadcast[] }>("/api/admin/broadcasts"),
    refetchInterval: (q) =>
      q.state.data?.items.some((b) => b.status === "running" || b.status === "pending")
        ? 1500
        : false,
  });

  const a = audiences.data;
  const targetCount = a?.[audience] ?? 0;

  async function send() {
    if (!text.trim()) return;
    if (!(await confirm(`${t.sendConfirm} → ${targetCount}`))) return;
    try {
      await api.post("/api/admin/broadcasts", {
        audience,
        media,
        text,
        button_enabled: renewBtn,
        button_text: renewBtn ? "Продлить со скидкой" : null,
        button_url: renewBtn ? "https://t.me" : null,
      });
      setText("");
      void qc.invalidateQueries({ queryKey: ["broadcasts"] });
      toast("✓");
    } catch (e) {
      toast(`${t.error}: ${(e as Error).message}`);
    }
  }

  return (
    <>
      <div className="page-head">
        <h1 className="h1">{t.broadcasts}</h1>
      </div>

      <div className="cols" style={{ marginBottom: 14 }}>
        <div className="card main-col">
          <div className="grid" style={{ gap: 14 }}>
            <div className="row" style={{ flexWrap: "wrap" }}>
              <span className="caps">{t.audience}</span>
              <Seg
                value={audience}
                options={[
                  { id: "all" as const, label: t.all, count: a?.all },
                  { id: "active" as const, label: t.active, count: a?.active },
                  { id: "trial" as const, label: t.trial, count: a?.trial },
                  { id: "expired" as const, label: t.expired, count: a?.expired },
                ]}
                onChange={setAudience}
              />
              <Seg
                value={media}
                options={[
                  { id: "text" as const, label: t.text },
                  { id: "photo" as const, label: t.photo },
                  { id: "video" as const, label: t.video },
                ]}
                onChange={setMedia}
              />
            </div>
            <textarea
              className="input"
              rows={7}
              placeholder="Текст рассылки (HTML-разметка Telegram)…"
              value={text}
              maxLength={4096}
              onChange={(e) => setText(e.target.value)}
            />
            <div className="row" style={{ justifyContent: "space-between", flexWrap: "wrap" }}>
              <label className="row" style={{ cursor: "pointer" }}>
                <Toggle on={renewBtn} onChange={setRenewBtn} />
                <span style={{ fontSize: 13 }}>{t.renewBtn}</span>
              </label>
              <span className="mono dim" style={{ fontSize: 11 }}>
                {text.length} / 4096
              </span>
            </div>
            <button className="btn primary" disabled={!text.trim()} onClick={send}>
              {t.send} → {targetCount.toLocaleString("ru-RU")}
            </button>
          </div>
        </div>

        {/* telegram preview */}
        <div className="card side-col" style={{ maxWidth: 420 }}>
          <div className="caps" style={{ marginBottom: 10 }}>
            {t.preview}
          </div>
          <div
            style={{
              background: "var(--panel2)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: 12,
            }}
          >
            {media !== "text" && (
              <div
                style={{
                  height: 120,
                  borderRadius: 6,
                  marginBottom: 8,
                  background:
                    "repeating-linear-gradient(45deg, var(--pill), var(--pill) 8px, var(--panel2) 8px, var(--panel2) 16px)",
                  display: "grid",
                  placeItems: "center",
                }}
              >
                <span className="caps">{media === "photo" ? t.photo : t.video}</span>
              </div>
            )}
            <div style={{ fontSize: 13.5, whiteSpace: "pre-wrap", minHeight: 40 }}>
              {text || <span className="dim">…</span>}
            </div>
            {renewBtn && (
              <div
                style={{
                  marginTop: 10,
                  border: "1px solid var(--border2)",
                  borderRadius: 6,
                  textAlign: "center",
                  padding: "8px 0",
                  fontSize: 13,
                }}
              >
                Продлить со скидкой
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="caps" style={{ marginBottom: 12 }}>
          {t.history}
        </div>
        <div className="grid" style={{ gap: 12 }}>
          {(history.data?.items ?? []).map((b) => {
            const running = b.status === "running" || b.status === "pending";
            return (
              <div key={b.id} className="grid" style={{ gap: 6 }}>
                <div className="row" style={{ justifyContent: "space-between", fontSize: 13 }}>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    <span className="mono dim">#{b.id}</span> {b.text.slice(0, 60)}
                  </span>
                  <span className="mono muted" style={{ flex: "0 0 auto" }}>
                    {running
                      ? `${t.sending} ${b.progress_pct}%`
                      : `${t.done} · ${b.sent}/${b.total} · ✕${b.failed}`}
                  </span>
                </div>
                <Prog pct={running ? b.progress_pct : 100} />
                <div className="caps">
                  {b.audience} · {dtTime(b.created_at)}
                </div>
              </div>
            );
          })}
          {history.data && history.data.items.length === 0 && <span className="dim">—</span>}
        </div>
      </div>
    </>
  );
}
