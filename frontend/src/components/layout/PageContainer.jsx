export default function PageContainer({ className = "", children }) {
  const classes = `page-container ${className}`.trim();
  return <div className={classes}>{children}</div>;
}
