export default function MetricGrid({ className = "", children }) {
  const classes = `layout-metric-grid ${className}`.trim();
  return <div className={classes}>{children}</div>;
}
