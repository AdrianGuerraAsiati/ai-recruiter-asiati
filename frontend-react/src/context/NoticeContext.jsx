import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

import Icon from "../components/ui/Icon";

const NoticeContext = createContext(null);

export function NoticeProvider({ children }) {
  const [notices, setNotices] = useState([]);
  const counter = useRef(0);

  const dismiss = useCallback((id) => {
    setNotices((current) => current.filter((notice) => notice.id !== id));
  }, []);

  const notify = useCallback(({ tone = "info", title = "", message, timeout = 5000 }) => {
    if (!message) return null;
    counter.current += 1;
    const id = `notice-${counter.current}`;
    setNotices((current) => [...current.slice(-3), { id, tone, title, message }]);
    if (timeout > 0) {
      window.setTimeout(() => dismiss(id), timeout);
    }
    return id;
  }, [dismiss]);

  const value = useMemo(() => ({ notify, dismiss }), [notify, dismiss]);

  return (
    <NoticeContext.Provider value={value}>
      {children}
      <div className="ui-notice-viewport" aria-label="Notificaciones">
        {notices.map((notice) => {
          const icon = notice.tone === "success" ? "check" : notice.tone === "error" ? "error" : notice.tone === "warning" ? "warning" : "info";
          return (
            <div key={notice.id} className={`ui-notice ui-notice--${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>
              <span className="ui-notice-icon" aria-hidden="true"><Icon name={icon} size={18} /></span>
              <div className="ui-notice-copy">
                {notice.title ? <strong>{notice.title}</strong> : null}
                <p>{notice.message}</p>
              </div>
              <button type="button" className="ui-notice-close" onClick={() => dismiss(notice.id)} aria-label="Cerrar notificación">×</button>
            </div>
          );
        })}
      </div>
    </NoticeContext.Provider>
  );
}

export function useNotice() {
  const context = useContext(NoticeContext);
  if (!context) throw new Error("useNotice must be used inside NoticeProvider");
  return context;
}
