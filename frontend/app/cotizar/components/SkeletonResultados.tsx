export default function SkeletonResultados({ n = 5 }: { n?: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
      {Array.from({ length: n }).map((_, i) => (
        <div
          key={i}
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border-default)",
            borderTop: i > 0 ? "none" : "1px solid var(--border-default)",
            padding: "16px 18px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            opacity: 1 - i * 0.15,
          }}
        >
          <div style={{ flex: 1 }}>
            <div style={{ width: "60%", height: 12, background: "var(--border-default)", marginBottom: 8 }} />
            <div style={{ width: "35%", height: 9, background: "var(--bg-base)" }} />
          </div>
          <div style={{ textAlign: "right" }}>
            <div style={{ width: 90, height: 14, background: "var(--border-default)", marginBottom: 8, marginLeft: "auto" }} />
            <div style={{ width: 70, height: 26, background: "var(--bg-base)", marginLeft: "auto" }} />
          </div>
        </div>
      ))}
    </div>
  );
}
