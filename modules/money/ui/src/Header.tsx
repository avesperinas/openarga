import { type AppBack, AppHeader } from "@openarga/ui";

declare const __MONEY_ICON__: string;

export const APP = { id: "money", name: "Money", icon: __MONEY_ICON__ };

export function ScreenHeader({ eyebrow, title, back }: { eyebrow?: string; title?: string; back?: AppBack }) {
  return <AppHeader app={APP} eyebrow={eyebrow} title={title} back={back} />;
}
