"use client";

import React from "react";

interface ErrorBoundaryState {
  hasError: boolean;
  message: string;
}

export default class ErrorBoundary extends React.Component<
  { children: React.ReactNode; label?: string },
  ErrorBoundaryState
> {
  constructor(props: { children: React.ReactNode; label?: string }) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, message: error?.message || "Unexpected rendering error" };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="terminal-panel border border-amber-500/35 p-4 text-xs text-amber-200">
          <div className="font-semibold">
            {this.props.label || "Panel"} temporarily interrupted — recovering safely.
          </div>
          <p className="mt-1 text-slate-400">{this.state.message}</p>
          <button
            type="button"
            onClick={() => this.setState({ hasError: false, message: "" })}
            className="mt-2.5 rounded-lg border border-amber-400/40 bg-amber-400/15 px-3 py-1 font-semibold text-amber-200 hover:bg-amber-400/25"
          >
            Reload Panel
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
