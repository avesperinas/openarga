import "@openarga/ui/tokens.css";
import "@openarga/ui/controls.css";
import "@openarga/ui/widget.css";
import "@openarga/ui/library.css";
import "@openarga/ui/health.css";
import "./app.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import { Backdrop, applyRemembered } from "./Backdrop";

applyRemembered();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Backdrop>
      <App />
    </Backdrop>
  </StrictMode>,
);
