/* App-wide UI state: theme, language, toasts, confirm dialog. */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { DICTS, type Dict, type Lang } from "../i18n";

type Confirm = { text: string; resolve: (ok: boolean) => void };

interface AppState {
  theme: "dark" | "light";
  setTheme: (t: "dark" | "light") => void;
  lang: Lang;
  setLang: (l: Lang) => void;
  t: Dict;
  toast: (msg: string) => void;
  confirm: (text: string) => Promise<boolean>;
}

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeRaw] = useState<"dark" | "light">(
    (localStorage.getItem("theme") as "dark" | "light") || "dark",
  );
  const [lang, setLangRaw] = useState<Lang>((localStorage.getItem("lang") as Lang) || "ru");
  const [toasts, setToasts] = useState<{ id: number; msg: string }[]>([]);
  const [confirmState, setConfirmState] = useState<Confirm | null>(null);
  const idRef = useRef(1);

  useEffect(() => {
    document.body.dataset.theme = theme;
  }, [theme]);

  const setTheme = useCallback((t: "dark" | "light") => {
    localStorage.setItem("theme", t);
    setThemeRaw(t);
  }, []);
  const setLang = useCallback((l: Lang) => {
    localStorage.setItem("lang", l);
    setLangRaw(l);
  }, []);

  const toast = useCallback((msg: string) => {
    const id = idRef.current++;
    setToasts((ts) => [...ts, { id, msg }]);
    setTimeout(() => setToasts((ts) => ts.filter((t) => t.id !== id)), 2600);
  }, []);

  const confirm = useCallback(
    (text: string) =>
      new Promise<boolean>((resolve) => {
        setConfirmState({ text, resolve });
      }),
    [],
  );

  const value = useMemo(
    () => ({ theme, setTheme, lang, setLang, t: DICTS[lang], toast, confirm }),
    [theme, setTheme, lang, setLang, toast, confirm],
  );

  const t = DICTS[lang];

  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="toasts">
        {toasts.map((x) => (
          <div key={x.id} className="toast">
            {x.msg}
          </div>
        ))}
      </div>
      {confirmState && (
        <div
          className="overlay"
          onClick={() => {
            confirmState.resolve(false);
            setConfirmState(null);
          }}
        >
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>{confirmState.text}</h3>
            <div className="row" style={{ justifyContent: "flex-end" }}>
              <button
                className="btn secondary"
                onClick={() => {
                  confirmState.resolve(false);
                  setConfirmState(null);
                }}
              >
                {t.cancel}
              </button>
              <button
                className="btn primary"
                onClick={() => {
                  confirmState.resolve(true);
                  setConfirmState(null);
                }}
              >
                {t.confirm}
              </button>
            </div>
          </div>
        </div>
      )}
    </Ctx.Provider>
  );
}

export function useApp(): AppState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useApp outside provider");
  return ctx;
}
