import { AppBackdrop, applyRemembered, useAppBackdrop } from "@openarga/ui";
import type { ReactNode } from "react";

export function Backdrop({ children }: { children: ReactNode }) {
  return (
    <AppBackdrop app="goals" className="goals-desktop">
      {children}
    </AppBackdrop>
  );
}

export const useBackdrop = useAppBackdrop;
export { applyRemembered };
