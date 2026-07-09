/* Screen — AI tech-support: train the AI (knowledge base + key) and test it live. */

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import { Field } from "../components/ui";
import { useApp } from "../state/app";

const MASK = "••••••••";

type Config = {
  enabled: boolean;
  has_key: boolean;
  model: string;
  knowledge_base: string;
  extra_prompt: string;
  default_kb: string;
};

export default function AiSupport() {
  const { t, toast } = useApp();
  const [cfg, setCfg] = useState<Config | null>(null);
  const [key, setKey] = useState("");
  const [dirty, setDirty] = useState(false);
  const [question, setQuestion] = useState("Здравствуйте, как подключиться на айфоне?");
  const [answer, setAnswer] = useState<{ reply: string | null; escalate: boolean } | null>(null);
  const [testing, setTesting] = useState(false);

  const data = useQuery({ queryKey: ["ai-support"], queryFn: () => api.get<Config>("/api/admin/ai-support") });

  useEffect(() => {
    if (data.data && !dirty) {
      setCfg(data.data);
      setKey(data.data.has_key ? MASK : "");
    }
  }, [data.data, dirty]);

  function patch(p: Partial<Config>) {
    setCfg((c) => (c ? { ...c, ...p } : c));
    setDirty(true);
  }

  async function save() {
    if (!cfg) return;
    try {
      const body: Record<string, unknown> = {
        enabled: cfg.enabled,
        model: cfg.model,
        knowledge_base: cfg.knowledge_base,
        extra_prompt: cfg.extra_prompt,
      };
      if (key !== MASK) body.api_key = key; // only send the key when actually changed
      await api.patch("/api/admin/ai-support", body);
      setDirty(false);
      toast(t.saved);
    } catch (e) {
      toast((e as Error).message);
    }
  }

  async function runTest() {
    if (!question.trim()) return;
    setTesting(true);
    setAnswer(null);
    try {
      const r = await api.post<{ reply: string | null; escalate: boolean }>(
        "/api/admin/ai-support/test",
        { question },
      );
      setAnswer(r);
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setTesting(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <h1 className="h1">🤖 {t.aiSupport}</h1>
        <div className="actions">
          {dirty && (
            <button className="btn primary" onClick={() => void save()}>
              {t.save}
            </button>
          )}
        </div>
      </div>

      {cfg && (
        <div className="cols">
          {/* left: training */}
          <div className="card main-col" style={{ maxWidth: 640 }}>
            <div className="grid" style={{ gap: 14 }}>
              <label className="row spread" style={{ cursor: "pointer" }}>
                <span>
                  <b>{t.aiEnable}</b>
                  <div className="dim" style={{ fontSize: 12.5 }}>{t.aiEnableHint}</div>
                </span>
                <input
                  type="checkbox"
                  checked={cfg.enabled}
                  onChange={(e) => patch({ enabled: e.target.checked })}
                />
              </label>

              <Field label={t.aiKey}>
                <input
                  className="input mono"
                  type="password"
                  value={key}
                  placeholder="sk-ant-…"
                  onFocus={() => key === MASK && setKey("")}
                  onChange={(e) => {
                    setKey(e.target.value);
                    setDirty(true);
                  }}
                />
                <div className="dim" style={{ fontSize: 12 }}>{t.aiKeyHint}</div>
              </Field>

              <Field label={t.aiModel}>
                <input
                  className="input mono"
                  value={cfg.model}
                  onChange={(e) => patch({ model: e.target.value })}
                />
              </Field>

              <div>
                <div className="row spread" style={{ marginBottom: 6 }}>
                  <span className="caps">{t.aiKb}</span>
                  <button
                    className="btn secondary sm"
                    onClick={() => patch({ knowledge_base: cfg.default_kb })}
                  >
                    {t.aiKbDefault}
                  </button>
                </div>
                <textarea
                  className="input"
                  style={{ minHeight: 320, resize: "vertical", fontSize: 13, lineHeight: 1.5 }}
                  placeholder={cfg.default_kb}
                  value={cfg.knowledge_base}
                  maxLength={20000}
                  onChange={(e) => patch({ knowledge_base: e.target.value })}
                />
                <div className="dim" style={{ fontSize: 12 }}>{t.aiKbHint}</div>
              </div>

              <Field label={t.aiExtra}>
                <textarea
                  className="input"
                  style={{ minHeight: 70, resize: "vertical" }}
                  value={cfg.extra_prompt}
                  maxLength={4000}
                  onChange={(e) => patch({ extra_prompt: e.target.value })}
                />
              </Field>

              {dirty && (
                <button className="btn primary" onClick={() => void save()}>
                  {t.save}
                </button>
              )}
            </div>
          </div>

          {/* right: live test */}
          <div className="side-col">
            <div className="card">
              <div className="caps" style={{ marginBottom: 8 }}>{t.aiTest}</div>
              <div className="dim" style={{ fontSize: 12.5, marginBottom: 10 }}>{t.aiTestHint}</div>
              <textarea
                className="input"
                style={{ minHeight: 70, resize: "vertical" }}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
              <button
                className="btn primary"
                style={{ marginTop: 10, width: "100%" }}
                disabled={testing || !cfg.has_key}
                onClick={() => void runTest()}
              >
                {testing ? t.aiThinking : t.aiTestBtn}
              </button>
              {!cfg.has_key && (
                <div className="dim" style={{ fontSize: 12, marginTop: 6 }}>{t.aiNeedKey}</div>
              )}
              {answer && (
                <div
                  className="card"
                  style={{ marginTop: 12, background: "var(--panel2, var(--panel))" }}
                >
                  {answer.escalate ? (
                    <div style={{ color: "var(--warn, #e0a800)" }}>⚠️ {t.aiEscalated}</div>
                  ) : (
                    <div style={{ whiteSpace: "pre-line", fontSize: 14 }}>{answer.reply}</div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
