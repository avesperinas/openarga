import { type AppBack, AppHeader } from "@openarga/ui";

declare const __RECIPES_ICON__: string;

export const APP = { id: "recipes", name: "Recipes", icon: __RECIPES_ICON__ };

export function ScreenHeader({ eyebrow, title, back }: { eyebrow?: string; title?: string; back?: AppBack }) {
  return <AppHeader app={APP} eyebrow={eyebrow} title={title} back={back} />;
}
