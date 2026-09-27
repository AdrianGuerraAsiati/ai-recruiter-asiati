// eslint-disable-next-line no-unused-vars
import React from "react";
import { Link } from "react-router-dom";

import { EmptyState } from "../components/ui/StatePanel";

export default function NotFound() {
  return (
    <div className="page system-state-page">
      <EmptyState
        icon="search"
        title="Esta página no existe"
        description="La dirección puede haber cambiado o el enlace está incompleto. Vuelve al inicio para continuar trabajando."
        action={<Link className="btn btn-primary" to="/dashboard">Ir al inicio</Link>}
      />
    </div>
  );
}
