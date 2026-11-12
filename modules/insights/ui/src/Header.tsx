import { type AppBack, AppHeader, type AppIdentity } from "@openarga/ui";
import { createContext, useContext } from "react";

declare const __INSIGHTS_ICON__: string;

export const NAME = "Insights";
export const APP: AppIdentity = { id: "insights", name: NAME, icon: __INSIGHTS_ICON__ };

export const AppContext = createContext<AppIdentity>(APP);
export const useApp = () => useContext(AppContext);

export function ScreenHeader({ eyebrow, title, back }: { eyebrow?: string; title?: string; back?: AppBack }) {
  return <AppHeader app={useApp()} eyebrow={eyebrow} title={title} back={back} />;
}
