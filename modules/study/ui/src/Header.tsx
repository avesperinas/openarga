import { type AppBack, AppHeader } from "@openarga/ui";

declare const __STUDY_ICON__: string;

export const APP = { id: "study", name: "Study", icon: __STUDY_ICON__ };

export function ScreenHeader({ eyebrow, title, back }: { eyebrow?: string; title?: string; back?: AppBack }) {
  return <AppHeader app={APP} eyebrow={eyebrow} title={title} back={back} />;
}
