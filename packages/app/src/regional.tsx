import { configureRegional, regionalFrom } from "@openarga/ui";
import { Fragment, type ReactNode } from "react";

import { usePreferences } from "./preferences";

export function RegionalRoot({ children }: { children: ReactNode }) {
  const preferences = usePreferences();
  const wanted = regionalFrom(preferences);
  configureRegional(wanted);
  // Formatters read the regional settings when they run, so a change remounts the app.
  return <Fragment key={`${wanted.locale}|${wanted.timeZone}|${wanted.currency}`}>{children}</Fragment>;
}
