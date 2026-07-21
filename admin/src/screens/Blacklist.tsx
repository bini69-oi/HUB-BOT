/* Screen 18. Чёрный список: block users by Telegram id (add / remove only). */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../api/client";
import { useApp } from "../state/app";

type Entry = { id: number; telegram_id: number; reason: string; created_at: string | null };

export default function Blacklist() {
  const { t, toast, confirm } = useApp();
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ["blacklist"],
    queryFn: () => api.get<{ items: Entry[] }>("/api/admin/blacklist"),
  });
  const [tid, setTid] = useState("");
  const [reason, setReason] = useState("");

  const refresh = () => void qc.invalidateQueries({ queryKey: ["blacklist"] });

  async function add() {
    const id = Number(tid.trim());
    if (!Number.isInteger(id) || id <= 0) {
      toast(t.blacklistBadId);
      return;
    }
    try {
      await api.post("/api/admin/blacklist", { telegram_id: id, reason: reason.trim() });
      setTid("");
      setReason("");
      refresh();
    } catch (e) {
      toast((e as Error).message);
    }
  }

  async function remove(e: Entry) {
    if (!(await confirm(t.blacklistRemoveConfirm))) return;
    try {
      await api.del(`/api/admin/blacklist/${e.telegram_id}`);
      refresh();
    } catch (err) {
      toast((err as Error).message);
    }
  }

  const items = list.data?.items ?? [];

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="h1">{t.blacklist}</h1>
          <div className="caps sub">{t.blacklistSub}</div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
          <input
            className="input num"
            style={{ width: 170 }}
            placeholder={t.blacklistTgId}
            value={tid}
            onChange={(e) => setTid(e.target.value)}
          />
          <input
            className="input"
            style={{ flex: 1, minWidth: 180 }}
            placeholder={t.blacklistReason}
            maxLength={256}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <button className="btn primary" onClick={add}>
            + {t.blacklistAdd}
          </button>
        </div>
      </div>

      <div className="tbl">
        <div className="tr" style={{ background: "var(--panel2)", gridTemplateColumns: "160px 1fr 140px auto" }}>
          <span className="caps">Telegram ID</span>
          <span className="caps">{t.blacklistReason}</span>
          <span className="caps">{t.added}</span>
          <span />
        </div>
        {items.map((e) => (
          <div key={e.id} className="tr" style={{ gridTemplateColumns: "160px 1fr 140px auto" }}>
            <span className="mono">{e.telegram_id}</span>
            <span className="muted">{e.reason || "-"}</span>
            <span className="dim" style={{ fontSize: 12 }}>
              {e.created_at ? new Date(e.created_at).toLocaleDateString() : "-"}
            </span>
            <button className="btn secondary sm" onClick={() => remove(e)}>
              {t.blacklistRemove}
            </button>
          </div>
        ))}
        {items.length === 0 && <div className="tr dim">{t.blacklistEmpty}</div>}
      </div>
    </>
  );
}
