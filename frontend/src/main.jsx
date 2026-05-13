import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./neraium-hardening.css";
import "./mobile-restore.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
import './mobile-sidebar-fix.css';
