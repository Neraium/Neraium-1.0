export default function PageContainer({ className = "", children, ...props }) {
  const classes = `page-container ${className}`.trim();
  return <div className={classes} {...props}>{children}</div>;
}
