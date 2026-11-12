import { type AppBack, AppHeader } from "@openarga/ui";

declare const __TRAINING_ICON__: string;

export const APP = { id: "training", name: "Training", icon: __TRAINING_ICON__ };

export function ScreenHeader({ eyebrow, title, back }: { eyebrow?: string; title?: string; back?: AppBack }) {
  return <AppHeader app={APP} eyebrow={eyebrow} title={title} back={back} />;
}
