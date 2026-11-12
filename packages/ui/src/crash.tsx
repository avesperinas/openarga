import * as React from "react";

import { Button } from "./controls";
import { EmptyState } from "./screen";

export class CrashBoundary extends React.Component<
  { home: string; children: React.ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: unknown): { error: Error } {
    return { error: error instanceof Error ? error : new Error(String(error)) };
  }

  componentDidCatch(error: unknown, info: React.ErrorInfo): void {
    console.error(error, info.componentStack);
  }

  render(): React.ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <main className="crash" role="alert">
        <EmptyState
          icon="alert"
          hue={1}
          title="Algo ha fallado en esta pantalla"
          action={{ label: "Volver a intentarlo", icon: "repeat", onClick: () => this.setState({ error: null }) }}
        >
          <p>Lo que has guardado sigue guardado. Si vuelve a pasar, este es el error:</p>
          <code className="crash-detail">{`${error.name}: ${error.message}`}</code>
        </EmptyState>
        <Button variant="plain" onClick={() => window.location.assign(this.props.home)}>
          Ir al inicio
        </Button>
      </main>
    );
  }
}
