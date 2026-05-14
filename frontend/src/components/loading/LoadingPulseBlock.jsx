export default function LoadingPulseBlock({ className = "" }) {
  const classes = `loading-pulse ${className}`.trim();
  return <div className={classes} aria-hidden="true" />;
}
