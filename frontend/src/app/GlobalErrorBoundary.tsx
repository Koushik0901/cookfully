import { Component, type ErrorInfo, type ReactNode } from "react";

import { BrandMark, ErrorRecovery } from "../components";

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
        <main className="utility-screen">
          <section className="utility-screen__card">
            <div className="utility-screen__brand"><BrandMark /><strong>Cookfully</strong></div>
            <p className="eyebrow">Your kitchen is still safe</p>
            <ErrorRecovery title="Cookfully hit an unexpected error" description="Reload the app to return to your kitchen. Your saved recipes and plans were not changed." onRetry={() => window.location.reload()} />
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}
