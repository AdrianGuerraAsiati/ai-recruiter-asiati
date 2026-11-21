// eslint-disable-next-line no-unused-vars
import React, { Component } from "react";

import { EmptyState } from "./ui/StatePanel";

function reloadPage() {
  window.location.reload();
}

/**
 * Captura errores de renderizado para que una excepción en una vista no deje
 * la aplicación en blanco. Cuando `resetKey` cambia (por ejemplo, la ruta), el
 * estado de error se limpia y se vuelve a intentar renderizar los hijos.
 */
class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null, resetKey: props.resetKey };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  static getDerivedStateFromProps(props, state) {
    if (props.resetKey !== state.resetKey) {
      return { error: null, resetKey: props.resetKey };
    }
    return null;
  }

  componentDidCatch(error, info) {
    if (typeof this.props.onError === "function") {
      this.props.onError(error, info);
    } else {
      console.error("Error de interfaz capturado", error, info?.componentStack);
    }
  }

  render() {
    if (!this.state.error) return this.props.children;

    const {
      title = "Algo salió mal al mostrar esta sección",
      description = "Ocurrió un error inesperado en la interfaz. Recarga la página para intentarlo de nuevo; si persiste, repórtalo indicando qué estabas haciendo.",
      className = "",
    } = this.props;

    return (
      <div className={`ui-error-boundary ${className}`.trim()} role="alert">
        <EmptyState
          icon="error"
          title={title}
          description={description}
          action={(
            <button type="button" className="btn btn-primary" onClick={reloadPage}>
              Recargar
            </button>
          )}
        />
      </div>
    );
  }
}

export default ErrorBoundary;
