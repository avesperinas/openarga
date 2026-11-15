import { ErrorState, Skeleton } from "@openarga/ui";
import { Component, type ComponentProps, type ReactNode, Suspense, lazy, useState } from "react";

import type { NoteEditor as Editor } from "./NoteEditor";
import { t } from "./lang";

const load = () => lazy(() => import("./NoteEditor").then((found) => ({ default: found.NoteEditor })));

class Caught extends Component<{ onRetry: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <ErrorState
        title={t("editor.missing")}
        detail={t("editor.missing_detail")}
        onRetry={() => {
          this.setState({ failed: false });
          this.props.onRetry();
        }}
      />
    );
  }
}

export function NoteEditor(props: ComponentProps<typeof Editor>) {
  const [Loaded, setLoaded] = useState(load);
  return (
    <Caught onRetry={() => setLoaded(load)}>
      <Suspense fallback={<Skeleton rows={6} />}>
        <Loaded {...props} />
      </Suspense>
    </Caught>
  );
}
