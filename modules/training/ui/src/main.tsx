import "@openarga/ui/tokens.css";
import "@openarga/ui/controls.css";
import "@openarga/ui/widget.css";
import "@openarga/ui/library.css";
import "@openarga/ui/health.css";
import "./app.css";

import { mountApp } from "@openarga/app";

import { App } from "./App";
import { Backdrop, applyRemembered } from "./Backdrop";
import { sharedQueue } from "./offline";

applyRemembered();

void mountApp(
  "training",
  <Backdrop>
    <App />
  </Backdrop>,
  { onPerson: (person) => sharedQueue().bindPerson(person) },
);
