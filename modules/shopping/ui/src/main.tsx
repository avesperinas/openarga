import "@openarga/ui/tokens.css";
import "@openarga/ui/controls.css";
import "@openarga/ui/widget.css";
import "@openarga/ui/library.css";
import "./app.css";

import { mountApp } from "@openarga/app";

import { queue } from "./api";
import { App } from "./App";
import { Backdrop, applyRemembered } from "./Backdrop";

applyRemembered();

void mountApp(
  "shopping",
  <Backdrop>
    <App />
  </Backdrop>,
  { onPerson: (person) => queue.bindPerson(person) },
);
