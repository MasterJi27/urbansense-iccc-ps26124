import { createContext, useContext, useState, useCallback, useRef, useEffect } from "react";

const ToastContext = createContext(null);

let nextId = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timersRef = useRef({});

  const remove = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    if (timersRef.current[id]) {
      clearTimeout(timersRef.current[id]);
      delete timersRef.current[id];
    }
  }, []);

  const add = useCallback(
    (message, type = "info") => {
      const id = ++nextId;
      setToasts((prev) => [...prev, { id, message, type }]);
      timersRef.current[id] = setTimeout(() => remove(id), 3200);
    },
    [remove]
  );

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      Object.values(timers).forEach(clearTimeout);
    };
  }, []);

  const toast = {
    success: (msg) => add(msg, "success"),
    error: (msg) => add(msg, "error"),
    info: (msg) => add(msg, "info"),
  };

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className="toast-container" role="status" aria-live="polite" aria-atomic="true">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`} role={t.type === "error" ? "alert" : "status"}>
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}

export default ToastProvider;
