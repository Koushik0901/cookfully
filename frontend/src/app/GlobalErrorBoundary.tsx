import { Component, type ErrorInfo, type ReactNode } from "react";

import { ErrorRecovery } from "../components";

interface State {
  failed: boolean;
}

export class GlobalErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Application render failed", { name: error.name, componentStack: info.componentStack });
  }

  render() {
    if (this.state.failed) {
      return (
        <main className="app-shell">
          <ErrorRecovery title="The planner hit an unexpected error" onRetry={() => window.location.reload()} />
        </main>
      );
    }
    return this.props.children;
  }
}
