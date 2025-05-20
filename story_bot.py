import os, asyncio, requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from telethon import TelegramClient, functions, types
import openai

# ─── Configuration ─────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", 0))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH")
TELEGRAM_CHANNEL = "your_channel_username"  # e.g. "my_public_channel"
FONT_PATH = "./Roboto-Thin.ttf"  # must support Cyrillic
OUTPUT_DIR = "./generated"
os.makedirs(OUTPUT_DIR, exist_ok=True)

openai.api_key = OPENAI_API_KEY


# ─── Step 1: Generate a short inspirational quote ───────────────────────────────
def generate_quote(topic: str) -> str:
	prompt = (
		f"Сформулируй на русском языке короткую (≤25 слов) "
		f"глубокую вдохновляющую цитату на тему: «{topic}»."
	)
	resp = openai.ChatCompletion.create(
		model="gpt-4",
		messages=[{"role": "user", "content": prompt}],
		max_tokens=60,
		temperature=0.7
	)
	return resp.choices[0].message.content.strip()


# ─── Step 2: Generate a square image via Stability API ──────────────────────────
def generate_image(prompt: str) -> Image.Image:
	url = "https://api.stability.ai/v2beta/stable-image/generate/sd3"
	headers = {
		"Authorization": f"Bearer {STABILITY_API_KEY}",
		"Accept": "image/jpeg"
	}
	data = {
		"prompt": prompt,
		"output_format": "jpeg"
	}
	r = requests.post(url, headers=headers, data=data, files={"none": ""})
	r.raise_for_status()
	return Image.open(BytesIO(r.content))


# ─── Step 3: Crop to 9×16 and overlay quote ──────────────────────────────────────
def overlay_text(img: Image.Image, text: str) -> str:
	# Crop to 9:16
	w, h = img.size
	target_ar = 9 / 16
	current_ar = w / h
	if current_ar > target_ar:
		new_w = int(h * target_ar)
		left = (w - new_w) // 2
		img = img.crop((left, 0, left + new_w, h))
	elif current_ar < target_ar:
		new_h = int(w / target_ar)
		top = (h - new_h) // 2
		img = img.crop((0, top, w, top + new_h))
	# Prepare for RGBA overlay
	img = img.convert("RGBA")
	draw, font = ImageDraw.Draw(img), ImageFont.truetype(FONT_PATH, sixty_five := 65)
	W, H = img.size
	# word-wrap
	margin = 40
	max_w = W - margin * 2
	lines, line = [], ""
	for word in text.split():
		test = f"{line} {word}".strip()
		if draw.textlength(test, font) <= max_w:
			line = test
		else:
			lines.append(line);
			line = word
	lines.append(line)
	# text block size
	ascent, descent = font.getmetrics()
	line_h = ascent + descent
	block_h = line_h * len(lines) + 10
	text_w = max(draw.textlength(l, font) for l in lines)
	# semi-transparent backdrop
	overlay = Image.new("RGBA", (int(text_w + 20), int(block_h)), (0, 0, 0, 160))
	img.paste(overlay, (margin, margin), overlay)
	# draw text
	y = margin + 5
	for l in lines:
		draw.text((margin + 10, y), l, font=font, fill=(255, 255, 255))
		y += line_h
	# save
	out_path = os.path.join(OUTPUT_DIR, "story_final.jpg")
	img.convert("RGB").save(out_path, "JPEG", quality=90)
	return out_path


# ─── Step 4: Post to Telegram Stories via Telethon ──────────────────────────────
async def post_story(image_path: str):
	client = TelegramClient("session", TELEGRAM_API_ID, TELEGRAM_API_HASH)
	await client.start()
	# upload + send
	file = await client.upload_file(image_path)
	await client(functions.stories.SendStoryRequest(
		peer=TELEGRAM_CHANNEL,
		media=types.InputMediaUploadedPhoto(
			file=file,
			spoiler=False,
			ttl_seconds=24 * 3600  # visible 24h
		),
		privacy_rules=[types.InputPrivacyValueAllowContacts()]
	))
	await client.disconnect()


# ─── Main Flow ─────────────────────────────────────────────────────────────────
def main():
	topic = input("Введите тему для цитаты: ").strip()
	quote = generate_quote(topic)
	print(f"Цитата: {quote}")

	img = generate_image(f"{topic}, minimalistic style, flat colors")
	print("Изображение сгенерировано.")

	final_path = overlay_text(img, quote)
	print(f"Наложили текст → {final_path}")

	asyncio.run(post_story(final_path))
	print("Сторис успешно опубликован!")


if __name__ == "__main__":
	main()
