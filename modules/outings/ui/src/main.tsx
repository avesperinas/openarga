import "@openarga/ui/tokens.css";
import "@openarga/ui/controls.css";
import "@openarga/ui/widget.css";
import "@openarga/ui/library.css";
import "@openarga/ui/map.css";
import "./app.css";

import { mountApp } from "@openarga/app";

import { App } from "./App";
import { Backdrop, applyRemembered } from "./Backdrop";
import { Localised } from "./Localised";

applyRemembered();

void mountApp(
  "outings",
  <Localised>
    <Backdrop>
      <App />
    </Backdrop>
  </Localised>,
);
