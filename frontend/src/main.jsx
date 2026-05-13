import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./neraium-hardening.css";
import "./styles/tokens.css";
import "./styles/typography.css";
import "./styles/elevation.css";
import "./styles/layout.css";
import "./styles/panels.css";
import "./styles/sidebar.css";
import "./styles/workspace-system-body.css";
import "./mobile-restore.css";
import "./mobile-sidebar-fix.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
