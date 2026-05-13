import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./neraium-hardening.css";
import "./desktop-orb-top.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
