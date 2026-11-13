# ADR 0007 — API HTTP de la Fase 2

**Fecha:** 2026-11-12
**Estado:** aceptado (entrega 2a; se amplía con 2b y 2c)

## Contexto

La Fase 2 conecta la libreta con el revisor: lazo → **Revisar** → transcripción y verificación. Hasta aquí el reconocimiento **nunca se había ejecutado contra el API real ni con letra real**: no había clave configurada y `backend/eval/cases/` estaba vacío. Los criterios de la Fase 0 seguían sin medirse.

## Decisiones

**Primero el tubo completo, luego lo fino.** La entrega 2a solo lleva una selección hasta el modelo y de vuelta. Las pistas, la edición de la transcripción y las marcas sobre la hoja esperan a ver cómo lee el modelo tinta real y a tener un banco de pruebas (2b), porque cualquier ajuste de prompt o de contrato debe medirse (SPEC §12.4).

**El banco de pruebas se arma con tinta de la app.** Lo que el modelo recibirá en producción es un PNG de trazos sobre blanco, no una foto de cuaderno. Los casos de `eval/` salen de revisiones reales guardadas por el backend.

**Los endpoints no reescriben nada.** `POST /api/check` guarda la imagen y llama a `recognize()` y `verify()` tal como lo hacen los CLIs (ADR 0001). El API solo añade lo que exige una frontera de red: token, límite de gasto, límite de tamaño y persistencia.

**Sin token no hay servicio.** Toda ruta exige `Authorization: Bearer <APP_TOKEN>`. Si `APP_TOKEN` está vacío el backend rechaza todo: un proxy abierto hacia un API de pago no debe ser el comportamiento por omisión. CORS admite solo el origen de la libreta y `localhost`.

**El límite mensual se aplica antes de gastar.** El gasto del mes se suma desde la tabla `UsageLog`; al alcanzar `MONTHLY_BUDGET_USD` la revisión se rechaza con un mensaje claro, sin llamar al modelo (SPEC §6.8).

**SQLite + SQLModel, con Alembic desde la primera tabla.** El backend migra al arrancar. Las tablas nunca se crean con `create_all` (SPEC §12.2).

**Un solo proceso verificador, precalentado.** Arrancar el subproceso de SymPy cuesta varios segundos en Windows. Medido con el modelo simulado: 4.6 s por revisión creando uno cada vez, cerca de 1 s reutilizándolo. El API mantiene uno vivo y lo protege con un candado.

**Modelo inicial: Claude Sonnet 5.5**, elegido por costo. Se compara contra otros cuando exista la línea base del banco de pruebas.

**Backend en la laptop con túnel rápido de Cloudflare** durante las pruebas. La dirección cambia en cada arranque, así que la app tiene un ajuste para pegarla. No afecta a las notas: IndexedDB depende del origen de la libreta, no del backend. El hosting definitivo es de la Fase 5.

**Las revisiones se guardan en los dos lados.** En el backend (`Check`, con la imagen y los trazos, para poder re-reconocer con modelos futuros) y en el iPad (tabla `reviews` de Dexie, versión 2) para leerlas sin conexión.

## Limitaciones conocidas de 2a

- No hay pista ni clasificación del error: el panel muestra lo que dice el verificador.
- La transcripción no se puede corregir todavía.
- Solo se revisa una selección de lazo, no la página entera.
- Sin conexión, Revisar avisa y no hace nada; la cola es de la Fase 3.
- No hay respaldo alterno de modelo si este declina una imagen: se muestra el error.
- El registro `usage.jsonl` de los CLIs y la tabla `UsageLog` del API conviven; el límite mensual usa solo la tabla.
