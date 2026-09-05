export default function Empty({ illustration, icon, title, description, hint, actionLabel, onAction, action, children, style }) {
  const visual = illustration ?? icon ?? "📭";
  return (
    <div className="empty" style={style}>
      {visual ? (
        <div style={{ fontSize: 28, lineHeight: 1, marginBottom: 8 }} aria-hidden="true">
          {visual}
        </div>
      ) : null}
      {title ? (
        <b style={{ display: "block", fontSize: 14 }}>{title}</b>
      ) : null}
      {description ? (
        <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
          {description}
        </div>
      ) : null}
      {hint ? (
        <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
          {hint}
        </div>
      ) : null}
      {action
        ? action
        : actionLabel && onAction
          ? (
            <button className="btn ghost btn-sm small" style={{ marginTop: 12 }} onClick={onAction}>
              {actionLabel}
            </button>
          )
          : null}
      {children}
    </div>
  );
}

export { Empty };
