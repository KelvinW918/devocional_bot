import os
import re
import feedparser
import requests
from datetime import datetime
import zoneinfo
from dotenv import load_dotenv
from google import genai
from google.genai.errors import ServerError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

# Cargar variables del entorno
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CHANNEL_ID = os.getenv("CHANNEL_ID")

# Mapeo de meses en español para validar la fecha
MESES_ESPANOL = {
    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
}


def obtener_fecha_hoy_venezuela():
    """Obtiene la fecha actual configurada en el huso horario de Venezuela."""
    tz = zoneinfo.ZoneInfo("America/Caracas")
    ahora = datetime.now(tz)
    dia = ahora.day
    mes = MESES_ESPANOL[ahora.month]
    anio = ahora.year
    return dia, mes, anio


def es_devocional_de_hoy(titulo):
    """
    Verifica que el título contenga 'Tu Tiempo con Dios'
    Y ADEMÁS la fecha coincida exactamente con el día de hoy (ej. 27 Septiembre 2026).
    """
    if not re.search(r"Tu\s+Tiempo\s+con\s+Dios", titulo, re.IGNORECASE):
        return False

    dia, mes, anio = obtener_fecha_hoy_venezuela()

    # Expresión regular que busca el día y el mes actual en el título
    # Ejemplo que matchea: "27 Septiembre", "27 de Septiembre", "27 Septiembre 2026"
    patron_fecha = rf"\b{dia}\s+(de\s+)?{mes}\b"

    if re.search(patron_fecha, titulo, re.IGNORECASE):
        return True

    return False


def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mensaje}

    print("[LOG] Intentando enviar mensaje a Telegram...")
    response = requests.post(url, json=payload)

    if response.status_code == 200:
        print("¡Mensaje enviado con éxito a Telegram!")
    else:
        print(f"¡Error al enviar el mensaje! Código: {response.status_code}")

    return response.json()


# Decorador con reintentos para soportar fallos 503 o caídas de Gemini
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=30),
    retry=retry_if_exception_type((ServerError, Exception)),
    reraise=True,
)
def generar_contenido_seguro(client, model_name, prompt):
    print(f"[LOG] Solicitando generación a Gemini ({model_name})...")
    return client.models.generate_content(model=model_name, contents=prompt)


def main():
    dia, mes, anio = obtener_fecha_hoy_venezuela()
    print(f"Buscando devocional para el día de hoy: {dia} de {mes} de {anio}...")

    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
    feed = feedparser.parse(feed_url)

    if not feed.entries:
        print("No se encontraron videos en el canal.")
        return

    devocional_entry = None
    for entry in feed.entries:
        if es_devocional_de_hoy(entry.title):
            devocional_entry = entry
            break

    if not devocional_entry:
        print(f"[AVISO] Aún no se ha publicado el devocional correspondiente a hoy ({dia} de {mes}).")
        print("Finalizando ejecución sin procesar videos antiguos.")
        return

    titulo_video = devocional_entry.title
    link_video = devocional_entry.link
    print(f" Devocional del día encontrado: {titulo_video}")

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""
    Eres un asistente teológico personal. Analiza el título del video devocional de hoy: "{titulo_video}".
    El título contiene la fecha y la referencia bíblica. Extrae la referencia bíblica exacta y redacta el devocional siguiendo estrictamente esta estructura, tono y formato de viñetas:

    📖 Mi tiempo con Dios: [REFERENCIA_BÍBLICA_EXTRAÍDA]

    ¿Cómo veo a Dios?
    [Tu reflexión corta y directa de cómo se ve a Dios en este pasaje, estilo personal]

    Mandatos
    - [Mandato 1 extraído del pasaje]
    - [Mandato 2...]
    - [Mandato 3...]

    Promesa
    - [Promesa específica que da Dios en el versículo]

    Mensaje Especial
    [Una frase o párrafo breve de revelación o comprensión profunda basada en el texto]

    Aplicación Personal
    [Un compromiso práctico y directo para el día a día]

    🔗 {link_video}
    """

    try:
        # Se usa el nombre del modelo validado en tu entorno
        response = generar_contenido_seguro(client, "gemini-3.8-flash", prompt)
        devocional_texto = response.text
    except Exception as e:
        print(f"[ERROR CRÍTICO] No se pudo generar el contenido tras varios reintentos con Gemini: {e}")
        return

    print("Enviando resultado a Telegram...")
    enviar_telegram(devocional_texto)
    print("¡Proceso completado con éxito!")


if __name__ == "__main__":
    main()