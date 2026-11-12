import { ErrorState, Skeleton } from "@openarga/ui";
import {
  Component,
  type ComponentProps,
  type ComponentType,
  type LazyExoticComponent,
  type ReactNode,
  Suspense,
  lazy,
  useState,
} from "react";

import type { GraphView as Graph } from "./GraphView";
import type { ImportScreen as Import } from "./ImportScreen";
import type { NoteEditor as Editor } from "./NoteEditor";

class Caught extends Component<{ what: string; onRetry: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <ErrorState
        title={`${this.props.what} no ha llegado`}
        detail="Sin conexión, o hay una versión nueva de Notebook."
        onRetry={() => {
          this.setState({ failed: false });
          this.props.onRetry();
        }}
      />
    );
  }
}

function deferred<P extends object>(what: string, load: () => Promise<ComponentType<P>>, rows = 6) {
  const make = () => lazy(() => load().then((found) => ({ default: found })));
  return function Deferred(props: P) {
    const [Loaded, setLoaded] = useState<LazyExoticComponent<ComponentType<P>>>(make);
    return (
      <Caught what={what} onRetry={() => setLoaded(make)}>
        <Suspense fallback={<Skeleton rows={rows} />}>
          <Loaded {...props} />
        </Suspense>
      </Caught>
    );
  };
}

export const NoteEditor = deferred<ComponentProps<typeof Editor>>("El editor", () =>
  import("./NoteEditor").then((found) => found.NoteEditor),
);

export const GraphView = deferred<ComponentProps<typeof Graph>>(
  "El grafo",
  () => import("./GraphView").then((found) => found.GraphView),
  4,
);

export const ImportScreen = deferred<ComponentProps<typeof Import>>("La importación", () =>
  import("./ImportScreen").then((found) => found.ImportScreen),
);
