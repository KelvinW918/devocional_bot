import os
import re
import feedparser
import requests
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

# Patrón regex estricto para validar la estructura del título
# Ejemplo compatible: "Tu Tiempo con Dios 26 Septiembre 2026 (1 Cronicas 15:16-29)"
PATRON_DEVOCIONAL = r"Tu\s+Tiempo\s+con\s+Dios"


def es_devocional_valido(titulo):
    """Verifica si el título contiene la frase clave del devocional."""
    return bool(re.search(PATRON_DEVOCIONAL, titulo, re.IGNORECASE))


def enviar_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": mensaje}

    print("[LOG] Intentando enviar mensaje a la URL de Telegram...")
    print(f"[LOG] CHAT_ID utilizado: {CHAT_ID}")

    response = requests.post(url, json=payload)

    print(f"[LOG] Código de estado HTTP de Telegram: {response.status_code}")
    print(f"[LOG] Respuesta completa de Telegram: {response.text}")

    if response.status_code == 200:
        print("¡Mensaje enviado con éxito a Telegram!")
    else:
        print("¡Error al enviar el mensaje!")

    return response.json()


# Función decorada con reintentos para manejar caídas o saturaciones de la API de Gemini (503)
@retry(
    stop=stop_after_attempt(5),  # Intentar hasta 5 veces
    wait=wait_exponential(multiplier=2, min=4, max=30),  # Espera progresiva (4s, 8s, 16s...)
    retry=retry_if_exception_type(ServerError),  # Reintentar si hay ServerError (503)
    reraise=True,
)
def generar_contenido_seguro(client, model_name, prompt):
    return client.models.generate_content(model=model_name, contents=prompt)


def main():
    print("Buscando el último video devocional del canal...")
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
    feed = feedparser.parse(feed_url)

    if not feed.entries:
        print("No se encontraron videos en el canal.")
        return

    # Buscar entre las últimas entradas del feed el primer video que coincida con el patrón
    devocional_entry = None
    for entry in feed.entries:
        if es_devocional_valido(entry.title):
            devocional_entry = entry
            break

    if not devocional_entry:
        print("No se encontró ningún video reciente con la estructura 'Tu Tiempo con Dios'. Expirando sin procesar...")
        return

    titulo_video = devocional_entry.title
    link_video = devocional_entry.link
    print(f"Devocional encontrado: {titulo_video}")

    print("Generando devocional con Gemini...")
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
        # Usamos un nombre de modelo estándar soportado por la API oficial
        response = generar_contenido_seguro(client, "gemini-3.8-flash", prompt)
        devocional_texto = response.text
    except Exception as e:
        print(f"[ERROR CRÍTICO] No se pudo generar el contenido tras varios reintentos: {e}")
        return

    print("Enviando resultado a Telegram...")
    enviar_telegram(devocional_texto)
    print("¡Proceso completado con éxito!")


if __name__ == "__main__":
    main()