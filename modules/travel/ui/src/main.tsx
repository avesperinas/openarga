import "@openarga/ui/tokens.css";
import "@openarga/ui/controls.css";
import "@openarga/ui/widget.css";
import "@openarga/ui/library.css";
import "@openarga/ui/map.css";
import "./app.css";

import { mountApp } from "@openarga/app";

import { queue } from "./api";
import { App } from "./App";
import { Backdrop, applyRemembered } from "./Backdrop";
import { adoptOldQueue, register } from "./offline";

applyRemembered();

void mountApp(
  "travel",
  <Backdrop>
    <App />
  </Backdrop>,
  {
    onPerson: async (person) => {
      await queue.bindPerson(person);
      await adoptOldQueue(person, queue);
      await register(person);
    },
  },
);
