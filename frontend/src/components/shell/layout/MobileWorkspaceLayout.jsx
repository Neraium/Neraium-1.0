export default function MobileWorkspaceLayout({ header, drawer, children }) {
  return (
    <>
      {header}
      {children}
      {drawer}
    </>
  );
}
