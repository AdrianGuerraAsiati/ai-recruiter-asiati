# Mapa de dominios y archivos compartidos

| Dominio | Zona principal | Posibles contratos compartidos |
| --- | --- | --- |
| Ranking / evaluaciones | `app/domains/ranking/`, `app/domains/evaluations/`, `frontend-react/src/pages/Ranking*` | modelos, router de ranking, jobs |
| Vacantes | `app/domains/jobs/`, `frontend-react/src/features/jobs/`, `frontend-react/src/pages/Jobs*` | ranking, Odoo, modelos |
| Candidatos | `app/domains/candidates/`, `frontend-react/src/pages/Candidates*` | ingesta, hiring, ranking |
| Empleados / contratación | `app/domains/employees/`, `app/domains/hiring/`, `frontend-react/src/pages/Employees*` | Odoo, onboarding, auth |
| Onboarding / documentos | `app/domains/training/`, `app/domains/employee_documents/` | empleados y RBAC |
| Asistencia | `app/domains/talent_id/` | empleados y Odoo |
| Agente de candidatos | `tools/indeed_resume_agent/`, `app/domains/candidate_ingestion/` | candidatos y API |
| Psicotécnicas | `app/domains/psychotechnical/` (si existe) | candidatos y permisos |

### Alta sensibilidad: requiere aviso y revisión cruzada
`app/models.py`, `app/crud.py`, `app/bootstrap.py`, `app/deps.py`, `alembic/**`, `frontend-react/src/api/**`, `frontend-react/src/context/**`, `.github/workflows/**`, `requirements.txt`, `frontend-react/package.json`.

La propiedad es **orientativa**, no exclusiva. La dependencia entre contratos importa tanto como coincidir en archivos.
