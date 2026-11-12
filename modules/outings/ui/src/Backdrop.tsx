import { AppBackdrop, applyRemembered, useAppBackdrop } from "@openarga/ui";
import type { ReactNode } from "react";

export function Backdrop({ children }: { children: ReactNode }) {
  return (
    <AppBackdrop app="outings" className="outings-desktop">
      {children}
    </AppBackdrop>
  );
}

export const useBackdrop = useAppBackdrop;
export { applyRemembered };
