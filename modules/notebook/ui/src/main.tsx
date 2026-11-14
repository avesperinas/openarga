import "@openarga/ui/tokens.css";
import "@openarga/ui/controls.css";
import "@openarga/ui/widget.css";
import "@openarga/ui/library.css";
import "@openarga/ui/notes.css";
import "./app.css";

import { mountApp } from "@openarga/app";
import { AppBackdrop, ToastHost, applyRemembered } from "@openarga/ui";

import { App } from "./App";
import { Localised } from "./Localised";

applyRemembered();

void mountApp(
  "notebook",
  <AppBackdrop app="notebook" className="notebook-desktop">
    <Localised>
      <ToastHost>
        <App />
      </ToastHost>
    </Localised>
  </AppBackdrop>,
);
