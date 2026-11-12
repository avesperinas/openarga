import { type AppBack, AppHeader } from "@openarga/ui";

declare const __HUB_ICON__: string;

export const APP = { id: "hub", name: "Hub", icon: __HUB_ICON__ };

export function ScreenHeader({ eyebrow, title, back }: { eyebrow?: string; title?: string; back?: AppBack }) {
  return <AppHeader app={APP} eyebrow={eyebrow} title={title} back={back} />;
}
