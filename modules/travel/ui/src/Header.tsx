import { type AppBack, AppHeader, AppHome } from "@openarga/ui";

declare const __TRAVEL_ICON__: string;

export const APP = { id: "travel", name: "Travel", icon: __TRAVEL_ICON__ };

export function ScreenHeader({ eyebrow, title, back }: { eyebrow?: string; title?: string; back?: AppBack }) {
  return <AppHeader app={APP} eyebrow={eyebrow} title={title} back={back} />;
}

export function HomeLink() {
  return <AppHome app={APP.id} className="travel-map-home glass" />;
}
