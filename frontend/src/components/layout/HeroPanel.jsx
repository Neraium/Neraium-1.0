export default function HeroPanel({ className = "", children }) {
  const classes = `hero-panel ${className}`.trim();
  return <section className={classes}>{children}</section>;
}
