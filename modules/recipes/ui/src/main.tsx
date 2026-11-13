import "@openarga/ui/tokens.css";
import "@openarga/ui/controls.css";
import "@openarga/ui/widget.css";
import "@openarga/ui/library.css";
import "./app.css";

import { mountApp } from "@openarga/app";

import { App } from "./App";
import { Localized } from "./i18n/Localized";
import { Backdrop, applyRemembered } from "./Backdrop";

applyRemembered();

void mountApp(
  "recipes",
  <Localized>
    <Backdrop>
      <App />
    </Backdrop>
  </Localized>,
);
