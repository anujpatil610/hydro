import "@fontsource-variable/hanken-grotesk";
import "@fontsource/geist-mono/400.css";
import "@fontsource/geist-mono/500.css";
import "@fontsource/geist-mono/600.css";
import "@fontsource/spectral/300.css";
import "@fontsource/spectral/400-italic.css";
import "@fontsource/spectral/400.css";
import "@fontsource/spectral/500.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/index.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("root element not found");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
