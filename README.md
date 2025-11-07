
# Impostor Royale — Prototipo de discusión por rondas

- **Máx. 10 jugadores por sala**
- **1–2 impostores (configurable al iniciar)**
- **La tripulación recibe la misma carta (palabra/tema)**; los impostores no reciben carta.
- **Voz/llamada o en persona**: el servidor solo lleva orden de turnos, rondas y votación.
- **La primera votación se habilita hasta completar 2 rondas** (dos vueltas desde quien inicia).

## Ejecutar

```bash
pip install -r requirements.txt
uvicorn server:app --port 8000 --reload
```
Abrir: http://localhost:8000/static/index.html  
Invitar con: `?room=ABCD` (ej., `http://localhost:8000/static/index.html?room=ABCD`)

## Flujo
1. Todos ingresan **Nombre** y **Sala** (sin registro).
2. Cuando haya ≥ 3, alguien pulsa **Iniciar** y elige 1–2 impostores.
3. El servidor asigna **roles** y **la misma carta** a tripulantes, y anuncia **quién empieza** (turno actual).
4. Convivencia/entrevista por voz o en persona. Usa **Siguiente turno** para rotar al siguiente orador.
5. Tras **2 rondas completas**, se habilita **Abrir votación**. Se vota haciendo **click** sobre un jugador en el círculo.
6. **Finalizar votación** hace el conteo. Se elimina al más votado (empate = nadie).
7. Gana la **Tripulación** si no quedan impostores; gana **Impostor** si son ≥ que la tripulación.

> Base educativa lista para estilizar a tema Clash Royale (arte, UI, sonidos).


## Despliegue "siempre encendido"

### Render
1. Conecta tu repo a Render y sube este proyecto.
2. Añade `render.yaml` en la raíz.
3. Plan **Starter** o superior para mantenerlo siempre encendido.
4. Render construirá con el `Dockerfile` y servirá tu web en HTTPS.

### Railway
1. Crea proyecto en Railway → "Deploy from Repo".
2. Railway detecta `railway.toml` y la orden de inicio.
3. Elige plan con 1 réplica siempre encendida.

### Fly.io
1. `fly launch` (usará `fly.toml` y `Dockerfile`).
2. Configura `min_machines_running = 1` para mantenerlo activo.
3. `fly deploy`.

### Google Cloud Run
1. Construye la imagen: `gcloud builds submit --tag gcr.io/PROJECT_ID/impostor-royale:latest`.
2. Despliega: `gcloud run deploy impostor-royale --image gcr.io/PROJECT_ID/impostor-royale:latest --region REGION --allow-unauthenticated --min-instances 1`.
3. Cloud Run mantendrá al menos 1 instancia activa.

> Todos estos métodos mantienen el servidor activo y sirven `static/landing.html` sin anuncios.


---

## 🚀 One‑Click Deploy (Render)
> Usa este botón cuando el código esté en tu repositorio. Solo **cambia** `YOUR_REPO_URL` por la URL de tu repo y haz clic.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=YOUR_REPO_URL)

**Cómo dejarlo a un clic:**
1) Sube este proyecto a un repo (GitHub).  
2) Reemplaza `YOUR_REPO_URL` en el botón por tu URL real.  
3) Haz clic en el botón y elige **Plan Starter** (o superior) para que quede **always on**.  
4) Render desplegará con el `Dockerfile` y `render.yaml` incluidos.

### Enlace directo útil (ejemplo de cómo se ve)
```
https://render.com/deploy?repo=https://github.com/tu_usuario/impostor-royale
```

> Si me compartes la URL final de tu repo, te devuelvo el botón listo ya con tu link.
