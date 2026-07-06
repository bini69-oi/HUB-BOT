/* App shell: sidebar (14 items, groups, badges, statuses) + topbar (crumbs,
   panel badge, theme/lang segments, avatar). */

import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { api, setToken } from "../api/client";
import { useApp } from "../state/app";
import { Seg } from "./ui";

type Me = { user_id: number; username: string; role: string };
type Counters = { all: number };
type TicketsResp = { open_count: number };

const VERSION = "CORE v0.1.0 · CABINET v0.1.0";

export default function Layout() {
  const { t, theme, setTheme, lang, setLang } = useApp();
  const loc = useLocation();
  const nav = useNavigate();

  const me = useQuery({ queryKey: ["me"], queryFn: () => api.get<Me>("/api/admin/auth/me") });
  const counters = useQuery({
    queryKey: ["users", "counters"],
    queryFn: () => api.get<Counters>("/api/admin/users/counters"),
    refetchInterval: 60_000,
  });
  const tickets = useQuery({
    queryKey: ["tickets"],
    queryFn: () => api.get<TicketsResp>("/api/admin/tickets"),
    refetchInterval: 60_000,
  });

  const items: {
    group?: string;
    num: string;
    path: string;
    label: string;
    badge?: number;
  }[] = [
    { num: "01", path: "/", label: t.dashboard },
    { group: t.gProduct, num: "02", path: "/users", label: t.users, badge: counters.data?.all },
    { num: "03", path: "/tariffs", label: t.tariffs },
    { num: "04", path: "/promos", label: t.promos },
    { group: t.gConstructor, num: "05", path: "/bot-buttons", label: t.botButtons },
    { num: "06", path: "/miniapp", label: t.miniapp },
    { group: t.gMarketing, num: "07", path: "/broadcasts", label: t.broadcasts },
    { num: "08", path: "/smart", label: t.smart },
    { num: "09", path: "/campaigns", label: t.campaigns },
    { group: t.gOps, num: "10", path: "/payments", label: t.payments },
    { num: "11", path: "/tickets", label: t.tickets, badge: tickets.data?.open_count },
    { group: t.gSystem, num: "12", path: "/servers", label: t.servers },
    { num: "13", path: "/settings", label: t.settings },
    { num: "14", path: "/maintenance", label: t.maintenance },
  ];

  const current = items.find(
    (i) => i.path === (loc.pathname === "/" ? "/" : "/" + loc.pathname.split("/")[1]),
  );

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="side-logo">
          <b>ADMIN CABINET</b>
        </div>
        <nav style={{ paddingBottom: 12 }}>
          {items.map((i) => (
            <span key={i.path}>
              {i.group && <div className="side-group caps">{i.group}</div>}
              <NavLink
                to={i.path}
                end={i.path === "/"}
                className={({ isActive }) => "side-item" + (isActive ? " active" : "")}
              >
                <span className="num">{i.num}</span>
                {i.label}
                {i.badge !== undefined && i.badge > 0 && (
                  <span className="badge">{i.badge.toLocaleString("ru-RU")}</span>
                )}
              </NavLink>
            </span>
          ))}
        </nav>
        <div className="side-footer">
          <span className="caps">
            <span className="status-dot" />
            API · ONLINE
          </span>
          <span className="caps">
            <span className="status-dot" />
            REMNAWAVE · SYNC
          </span>
          <span className="caps">{VERSION}</span>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <span className="crumbs">ADMIN / {current?.label ?? ""}</span>
          <span className="spacer" />
          <span className="cap-pill">● REMNAWAVE · OK</span>
          <Seg
            value={theme}
            options={[
              { id: "dark" as const, label: "DARK" },
              { id: "light" as const, label: "LIGHT" },
            ]}
            onChange={setTheme}
          />
          <Seg
            value={lang}
            options={[
              { id: "ru" as const, label: "RU" },
              { id: "en" as const, label: "EN" },
            ]}
            onChange={setLang}
          />
          <div className="row" style={{ gap: 8 }}>
            <div className="avatar-sq">
              {(me.data?.username ?? "??").slice(0, 2).toUpperCase()}
            </div>
            <div style={{ lineHeight: 1.2 }}>
              <div style={{ fontSize: 12.5 }}>@{me.data?.username}</div>
              <div className="caps">{me.data?.role}</div>
            </div>
            <button
              className="btn secondary sm"
              title={t.logout}
              onClick={() => {
                setToken(null);
                nav("/login");
              }}
            >
              ⎋
            </button>
          </div>
        </header>
        <main className="content">
          <div className="content-inner">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
