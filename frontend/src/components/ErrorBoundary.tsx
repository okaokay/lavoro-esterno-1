import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

// Class component because React only supports error boundaries via
// getDerivedStateFromError/componentDidCatch — there is no hook equivalent.
// Wraps the whole app (see main.tsx) so a rendering crash anywhere shows a
// recoverable fallback instead of a blank white page.
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // No error-reporting service is wired up in this scaffold (see
    // PROGETTO.md § 9 Observability) — console.error is the only place
    // this is currently visible, deliberately not swallowed silently.
    console.error("Unhandled rendering error caught by ErrorBoundary:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="min-h-screen flex items-center justify-center bg-background p-6">
        <div className="max-w-md w-full bg-surface-container-lowest border border-border rounded-lg shadow-sm p-6 text-center space-y-4">
          <span className="material-symbols-outlined text-error text-4xl" aria-hidden="true">
            error
          </span>
          <div>
            <h1 className="text-headline-sm text-on-surface">Qualcosa è andato storto</h1>
            <p className="text-body-md text-on-surface-variant mt-1">
              An unexpected error occurred while rendering this page. Reloading usually fixes it.
            </p>
          </div>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-primary text-on-primary rounded-DEFAULT text-label-sm font-semibold hover:bg-primary-container transition-colors"
          >
            Reload page
          </button>
        </div>
      </div>
    );
  }
}
