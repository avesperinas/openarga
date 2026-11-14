import "@openarga/ui/tokens.css";
import "@openarga/ui/controls.css";
import "@openarga/ui/widget.css";
import "@openarga/ui/library.css";
import "./app.css";

import { mountApp } from "@openarga/app";

import { queue } from "./api";
import { App } from "./App";
import { Backdrop, applyRemembered } from "./Backdrop";
import { Localized } from "./i18n/Localized";

applyRemembered();

void mountApp(
  "shopping",
  <Localized>
    <Backdrop>
      <App />
    </Backdrop>
  </Localized>,
  { onPerson: (person) => queue.bindPerson(person) },
);
