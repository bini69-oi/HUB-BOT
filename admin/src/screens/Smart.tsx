/* Screen 08. Умные рассылки: win-back funnel + RF holiday promo calendar.
   (Expiry reminders moved to their own hour-based screen, «Напоминания».) */

import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import { Field, Seg, Toggle } from "../components/ui";
import { useApp } from "../state/app";

type Holiday = {
  id: number;
  date: string;
  name: string;
  enabled: boolean;
  reward_type: "discount" | "days" | "balance";
  value: number;
  send_time: string;
  results: Record<string, { sent?: number; conv?: number }>;
};
type WinbackStep = {
  id: number;
  offset_days: number;
  text: string;
  discount_pct: number;
  send_time: string;
  enabled: boolean;
};

export default function Smart() {
  const { t, toast } = useApp();
  const qc = useQueryClient();

  const holidays = useQuery({
    queryKey: ["holidays"],
    queryFn: () => api.get<{ items: Holiday[] }>("/api/admin/holidays"),
  });
  const winback = useQuery({
    queryKey: ["winback"],
    queryFn: () => api.get<{ items: WinbackStep[] }>("/api/admin/winback"),
  });

  async function patchHoliday(h: Holiday, p: Partial<Holiday>) {
    try {
      await api.patch(`/api/admin/holidays/${h.id}`, p);
      void qc.invalidateQueries({ queryKey: ["holidays"] });
    } catch (e) {
      toast((e as Error).message);
    }
  }

  async function patchStep(s: WinbackStep, p: Partial<WinbackStep>) {
    try {
      await api.patch(`/api/admin/winback/${s.id}`, p);
      void qc.invalidateQueries({ queryKey: ["winback"] });
    } catch (e) {
      toast((e as Error).message);
    }
  }

  async function addStep() {
    const steps = winback.data?.items ?? [];
    const last = steps.at(-1);
    try {
      await api.post("/api/admin/winback", {
        offset_days: last ? last.offset_days * 2 : 3,
        text: "Мы скучаем! Вернитесь со скидкой {discount}% на любой тариф.",
        discount_pct: Math.min(100, (last?.discount_pct ?? 5) + 5),
      });
      void qc.invalidateQueries({ queryKey: ["winback"] });
    } catch (e) {
      toast((e as Error).message);
    }
  }

  async function deleteStep(s: WinbackStep) {
    try {
      await api.del(`/api/admin/winback/${s.id}`);
      void qc.invalidateQueries({ queryKey: ["winback"] });
    } catch (e) {
      toast((e as Error).message);
    }
  }

  // Nearest upcoming enabled holiday.
  const now = new Date();
  const nearest = (holidays.data?.items ?? [])
    .filter((h) => h.enabled)
    .map((h) => {
      const [d, m] = h.date.split(".").map(Number);
      const dt = new Date(now.getFullYear(), m - 1, d);
      if (dt < now) dt.setFullYear(dt.getFullYear() + 1);
      return { h, dt };
    })
    .sort((a, b) => a.dt.getTime() - b.dt.getTime())[0];

  return (
    <>
      <div className="page-head">
        <h1 className="h1">{t.smart}</h1>
      </div>

      <a
        href="#/reminders"
        className="card"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          marginBottom: 14,
          textDecoration: "none",
          color: "var(--text)",
        }}
      >
        <span style={{ fontSize: 22 }}>⏳</span>
        <span style={{ flex: 1, fontSize: 13.5 }}>{t.remindersMoved}</span>
        <span className="btn secondary sm">{t.openReminders} →</span>
      </a>

      <div className="card" style={{ marginBottom: 14 }}>
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
          <span className="caps">{t.winbackFunnel}</span>
          <button className="btn secondary sm" onClick={() => void addStep()}>
            + {t.winbackAdd}
          </button>
        </div>
        <div className="grid" style={{ gap: 14 }}>
          {(winback.data?.items ?? []).map((s) => (
            <div key={s.id} className="grid" style={{ gap: 8 }}>
              <div className="row" style={{ flexWrap: "wrap" }}>
                <Field label={t.winbackDays}>
                  <input
                    className="input num"
                    style={{ width: 74 }}
                    type="number"
                    defaultValue={s.offset_days}
                    onBlur={(e) => {
                      const v = Number(e.target.value) || 0;
                      if (v >= 1 && v !== s.offset_days) void patchStep(s, { offset_days: v });
                    }}
                  />
                </Field>
                <Field label={`${t.discount} %`}>
                  <input
                    className="input num"
                    style={{ width: 74 }}
                    type="number"
                    defaultValue={s.discount_pct}
                    onBlur={(e) => {
                      const v = Number(e.target.value) || 0;
                      if (v >= 0 && v <= 100 && v !== s.discount_pct)
                        void patchStep(s, { discount_pct: v });
                    }}
                  />
                </Field>
                <Field label={t.timeMsk}>
                  <input
                    className="input mono"
                    style={{ width: 90 }}
                    defaultValue={s.send_time}
                    onBlur={(e) => {
                      if (e.target.value !== s.send_time)
                        void patchStep(s, { send_time: e.target.value });
                    }}
                  />
                </Field>
                <span style={{ flex: 1 }} />
                <Toggle on={s.enabled} onChange={(v) => void patchStep(s, { enabled: v })} />
                <button className="btn danger sm" onClick={() => void deleteStep(s)}>
                  ✕
                </button>
              </div>
              <Field label={`${t.msgText} · {discount}`}>
                <textarea
                  className="input"
                  rows={2}
                  defaultValue={s.text}
                  onBlur={(e) => {
                    const v = e.target.value.trim();
                    if (v && v !== s.text) void patchStep(s, { text: v });
                  }}
                />
              </Field>
            </div>
          ))}
          {(winback.data?.items ?? []).length === 0 && (
            <span className="dim" style={{ fontSize: 13 }}>
              {t.winbackEmpty}
            </span>
          )}
        </div>
      </div>

      <div className="card">
        <div className="row" style={{ justifyContent: "space-between", marginBottom: 12 }}>
          <span className="caps">{t.holidayCalendar}</span>
          {nearest && (
            <span className="caps">
              {t.nearest}: {nearest.h.date} · {nearest.h.name}
            </span>
          )}
        </div>
        <div className="grid" style={{ gap: 10 }}>
          {(holidays.data?.items ?? []).map((h) => {
            const past = Object.keys(h.results).length > 0;
            const lastYear = past ? Object.keys(h.results).sort().at(-1) : null;
            const res = lastYear ? h.results[lastYear] : null;
            return (
              <div key={h.id} className="row" style={{ flexWrap: "wrap", fontSize: 13 }}>
                <span className="mono" style={{ width: 52 }}>
                  {h.date}
                </span>
                <span style={{ width: 190, overflow: "hidden", textOverflow: "ellipsis" }}>
                  {h.name}
                </span>
                <Seg
                  value={h.reward_type}
                  options={[
                    { id: "discount" as const, label: t.discount },
                    { id: "days" as const, label: t.rewardDays },
                    { id: "balance" as const, label: "₽" },
                  ]}
                  onChange={(reward_type) => void patchHoliday(h, { reward_type })}
                />
                <input
                  className="input num"
                  style={{ width: 74 }}
                  type="number"
                  defaultValue={h.value}
                  onBlur={(e) => {
                    const v = Number(e.target.value) || 0;
                    if (v !== h.value) void patchHoliday(h, { value: v });
                  }}
                />
                <span className="dim" style={{ flex: 1, minWidth: 120, fontSize: 12 }}>
                  {res
                    ? `${res.sent ?? 0} · +${res.conv ?? 0} продлений`
                    : `${t.planned} · ${h.send_time}`}
                </span>
                <Toggle on={h.enabled} onChange={(v) => void patchHoliday(h, { enabled: v })} />
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
