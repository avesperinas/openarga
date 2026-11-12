import { AppBackdrop, applyRemembered, useAppBackdrop } from "@openarga/ui";
import type { ReactNode } from "react";

export function Backdrop({ children }: { children: ReactNode }) {
  return (
    <AppBackdrop app="recipes" className="recipes-desktop">
      {children}
    </AppBackdrop>
  );
}

export const useBackdrop = useAppBackdrop;
export { applyRemembered };
