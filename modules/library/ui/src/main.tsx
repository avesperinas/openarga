import "@openarga/ui/tokens.css";
import "@openarga/ui/controls.css";
import "@openarga/ui/widget.css";
import "@openarga/ui/library.css";
import "./app.css";

import { mountApp } from "@openarga/app";

import { App } from "./App";
import { Backdrop, applyRemembered } from "./Backdrop";

applyRemembered();

void mountApp(
  "library",
  <Backdrop>
    <App />
  </Backdrop>,
);
