import { ErrorState, Screen, Skeleton } from "@openarga/ui";
import { Component, type ComponentType, type ReactNode, Suspense, lazy, useState } from "react";

class Caught extends Component<{ onRetry: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <ErrorState
        title="Esta parte de Travel no ha llegado"
        detail="Sin conexión, o hay una versión nueva de Travel."
        onRetry={() => {
          this.setState({ failed: false });
          this.props.onRetry();
        }}
      />
    );
  }
}

export function later<P extends object>(
  load: () => Promise<ComponentType<P>>,
  { screen = true, rows = 6 }: { screen?: boolean; rows?: number } = {},
): ComponentType<P> {
  const fresh = () => lazy(() => load().then((found) => ({ default: found })));
  let shared = fresh();
  function Later(props: P) {
    const [Loaded, setLoaded] = useState(() => shared);
    const waiting = <Skeleton rows={rows} />;
    return (
      <Caught
        onRetry={() => {
          shared = fresh();
          setLoaded(() => shared);
        }}
      >
        <Suspense fallback={screen ? <Screen>{waiting}</Screen> : waiting}>
          <Loaded {...props} />
        </Suspense>
      </Caught>
    );
  }
  return Later;
}
