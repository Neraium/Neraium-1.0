export default function SectionCard({ className = "", children }) {
  const classes = `section-card ${className}`.trim();
  return <article className={classes}>{children}</article>;
}
