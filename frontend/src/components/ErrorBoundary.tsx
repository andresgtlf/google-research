import { Component, type ErrorInfo, type ReactNode } from "react";
import Button from "./Button";

interface ErrorBoundaryProps {
  children: ReactNode;
  /** Shown above the reset button, e.g. "the results view". */
  area?: string;
  /** Called when the user clicks "Start over" from the crash screen. Should
   * clear any persisted job state so the next load starts clean. */
  onReset?: () => void;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/**
 * Class components are the only way to catch render errors in React; there
 * is no hook equivalent. This is the fix for the CRITICAL bug where an
 * unguarded `new URL(...)` (or any other render-time throw) in a
 * deeply-nested evidence-table cell blanked the entire page after a
 * 20-minute job, with no way back except a full reload.
 */
export default class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Server-side logging is out of scope for this static frontend; at
    // minimum this keeps the failure visible in the browser console
    // instead of silently vanishing along with the blanked page.
    console.error("Unhandled render error", error, info.componentStack);
  }

  private handleReset = (): void => {
    this.props.onReset?.();
    this.setState({ error: null });
  };

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    return (
      <div className="mx-auto max-w-2xl px-6 py-10">
        <div className="rounded-lg border-l-4 border-[var(--color-danger)] bg-[var(--color-danger-bg)] p-6">
          <h2 className="text-h3 text-[var(--color-danger-text)]">
            {this.props.area ? `Something failed in ${this.props.area}` : "Something failed"}
          </h2>
          <p className="mt-2 text-body text-[var(--color-danger-text)]">
            {error.message || "The page hit an unexpected error while rendering."}
            {" "}Your job may still be running on the server, but this tab could not
            display it. Starting over will not cancel the job.
          </p>
          <Button variant="primary" className="mt-4" onClick={this.handleReset}>
            Start over
          </Button>
        </div>
      </div>
    );
  }
}
