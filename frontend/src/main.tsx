import "@fontsource-variable/afacad-flux";
import "@fontsource-variable/inclusive-sans";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import { registerProgressiveWebApp } from "./app/pwa";
import "./styles/globals.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("Application root element is missing");
}

registerProgressiveWebApp();

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
