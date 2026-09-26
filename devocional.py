import os
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


def enviar_telegram(mensaje):
  url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
  # Quitamos parse_mode para evitar que caracteres especiales rompan el formato de Telegram
  payload = {"chat_id": CHAT_ID, "text": mensaje}

  print(f"[LOG] Intentando enviar mensaje a la URL de Telegram...")
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
    wait=wait_exponential(
        multiplier=2, min=4, max=30
    ),  # Espera progresiva (4s, 8s, 16s...)
    retry=retry_if_exception_type(
        ServerError
    ),  # Reintentar específicamente si hay ServerError (503)
    reraise=True,
)
def generar_contenido_seguro(client, model_name, prompt):
  return client.models.generate_content(model=model_name, contents=prompt)


def main():
  print("Buscando el último video del canal...")
  feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
  feed = feedparser.parse(feed_url)

  if not feed.entries:
    print("No se encontraron videos en el canal.")
    return

  latest_video = feed.entries[0]
  titulo_video = latest_video.title
  link_video = latest_video.link
  print(f"Video encontrado: {titulo_video}")

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
    # Usamos la función protegida con reintentos (manteniendo tu modelo o ajustándolo si es necesario)
    response = generar_contenido_seguro(client, "gemini-3.8-flash", prompt)
    devocional_texto = response.text
  except Exception as e:
    print(
        f"[ERROR CRÍTICO] No se pudo generar el contenido tras varios"
        f" reintentos: {e}"
    )
    return

  print("Enviando resultado a Telegram...")
  enviar_telegram(devocional_texto)
  print("¡Proceso completado con éxito!")


if __name__ == "__main__":
  main()