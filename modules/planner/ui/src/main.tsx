import "@openarga/ui/tokens.css";
import "@openarga/ui/controls.css";
import "@openarga/ui/widget.css";
import "@openarga/ui/library.css";
import "@openarga/ui/calendar.css";
import "./app.css";

import { mountApp } from "@openarga/app";
import { AppBackdrop, applyRemembered, ToastHost } from "@openarga/ui";

import { App } from "./App";

applyRemembered();

void mountApp(
  "planner",
  <AppBackdrop app="planner" className="planner-desktop">
    <ToastHost>
      <App />
    </ToastHost>
  </AppBackdrop>,
);
