// eslint-disable-next-line no-unused-vars
import React from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "../components/ui/StatePanel";

export default function Forbidden() {
  return (
    <div className="page system-state-page">
      <EmptyState
        icon="warning"
        title="Acceso restringido"
        description="Tu cuenta está activa, pero no tiene permiso para abrir esta sección. Puedes volver al inicio o solicitar el acceso al responsable correspondiente."
        action={<Link className="btn btn-primary" to="/dashboard">Volver al inicio</Link>}
      />
    </div>
  );
}
