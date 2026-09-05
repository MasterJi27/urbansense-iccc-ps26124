export function Skeleton({ width = "100%", height = 14, radius = 8, style = {}, className = "" }) {
  return (
    <div
      className={`skeleton ${className}`.trim()}
      style={{ width, height, borderRadius: radius, ...style }}
      aria-hidden="true"
    />
  );
}

export function SkeletonCard({ lines = 3 }) {
  return (
    <div className="card" role="status" aria-label="Loading">
      <Skeleton width="40%" height={12} style={{ marginBottom: 12 }} />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} height={14} style={{ marginBottom: 8 }} />
      ))}
      <Skeleton width="68%" height={14} />
    </div>
  );
}

export function SkeletonKPI() {
  return (
    <div className="card" role="status" aria-label="Loading">
      <Skeleton width="55%" height={10} style={{ marginBottom: 14 }} />
      <Skeleton width="40%" height={28} style={{ marginBottom: 8 }} />
      <Skeleton width="75%" height={12} />
    </div>
  );
}

export function SkeletonGrid({ count = 4 }) {
  return (
    <div className="kpis" role="status" aria-label="Loading">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonKPI key={i} />
      ))}
    </div>
  );
}

export default Skeleton;
