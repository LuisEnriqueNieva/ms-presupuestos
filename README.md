# ms-presupuestos

Microservicio de Presupuestos y Gastos del SaaS PPM (multi-tenant, serverless).

## Antes de desplegar

1. Desplegados: `ms-auth`, `ms-proyectos` (y `ms-tareas`).
2. En `serverless.yml`, seccion `custom`, cambiar los 3 correos (uno por tenant).
3. `serverless deploy`
4. Abrir los correos de AWS Notifications y confirmar cada suscripcion ("Confirm subscription").

Crea: 3 Lambdas, tablas `t_presupuestos` y `t_gastos`, tema SNS `tema-presupuestos`,
cola SQS `cola-presupuestos-asignaciones` (+ DLQ), la suscripcion de `cola-proyectos-eventos`
y 3 suscripciones de correo con filtro por tenant.

Los `tenant_id` van en MAYUSCULAS: ACM, ORACLE, LUDOTECA (el filtro de correo distingue mayusculas).

## Rutas (todas piden la cabecera `Authorization`)

| Ruta | Lambda | Cuerpo |
| --- | --- | --- |
| POST /presupuestos/crear | Presupuestos (`presupuestos.py`) | proyecto_id, monto_total |
| POST /presupuestos/buscar | Presupuestos (`presupuestos.py`) | proyecto_id |
| PUT /presupuestos/modificar | Presupuestos (`presupuestos.py`) | proyecto_id, monto_total |
| POST /gastos/registrar | Gastos (`gastos.py`) | proyecto_id, monto, concepto?, fecha? |
| POST /gastos/listar | Gastos (`gastos.py`) | proyecto_id?, limit?, last_key? |

Sin ruta: `ProcesarAsignaciones` (lo dispara SQS).

## Eventos

- Publica `PresupuestoExcedido` en `tema-presupuestos`, UNA sola vez, cuando
  `gasto_acumulado` supera `monto_total`. Lo reciben Proyectos (marca el proyecto como
  EXCEDIDO) y el correo del tenant. Priorizacion lo recibira cuando se despliegue
  (su suscripcion la declara ms-priorizacion).
- Consume `AsignacionCreada` (de ms-recursos): suma el `costo` de la asignacion a
  `costo_proyectado`. Hasta desplegar Recursos, esta cola no recibe nada.

## Prueba rapida

1. Login y poner el token en `Authorization`.
2. `POST /presupuestos/crear` con `{"proyecto_id": "<id>", "monto_total": 1000}`.
3. `POST /gastos/registrar` con `{"proyecto_id": "<id>", "monto": 600, "concepto": "Licencias"}`.
4. `POST /gastos/registrar` con `{"proyecto_id": "<id>", "monto": 500, "concepto": "Servidores"}`
   -> `estado_presupuesto` = EXCEDIDO, llega el correo, y `POST /proyectos/buscar`
   muestra `estado_presupuesto` = EXCEDIDO (unos segundos despues).
5. Un tercer gasto NO manda otro correo.

## Estructura de Lambdas (3)

Una Lambda atiende varios endpoints: el codigo elige la funcion segun la ruta (`requestPath` de API Gateway).

- `presupuestos.py` -> Lambda **Presupuestos**: /presupuestos/crear, /presupuestos/buscar, /presupuestos/modificar
- `gastos.py` -> Lambda **Gastos**: /gastos/registrar, /gastos/listar
- `procesar_asignaciones.py` (trigger SQS).

`comun.py` es codigo compartido (token, respuestas, helpers), no es una Lambda.
