import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("[ErrorBoundary]", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="card" style={{ margin: 12 }}>
          <div className="card-title">Algo se rompió en esta vista</div>
          <div className="card-sub" style={{ fontFamily: "var(--mono)", color: "var(--err)" }}>
            {String(this.state.error?.message || this.state.error)}
          </div>
          <button
            className="btn btn-primary"
            onClick={() => {
              this.setState({ error: null });
              this.props.onReset?.();
            }}
          >
            Reintentar
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
