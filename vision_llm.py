import os
import re
import base64
import pymupdf

from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    api_key=os.environ["CHUTES_API_KEY"],
    base_url="https://llm.chutes.ai/v1",
)

MODEL = "Qwen/Qwen3.5-397B-A17B-TEE"

FORMAT_GAMBAR = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def bersihkan_output(teks):
    teks = "\n".join(baris.strip() for baris in teks.splitlines())
    teks = re.sub(r"\n{3,}", "\n\n", teks)
    return teks.strip()


def analisis_dokumen(path, pertanyaan, max_pages=None):
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"File tidak ditemukan: {path}")

    ekstensi = path.suffix.lower()

    if ekstensi != ".pdf" and ekstensi not in FORMAT_GAMBAR:
        raise ValueError("Format harus PDF, PNG, JPG, JPEG, atau WEBP.")

    # Buka PDF atau gambar menggunakan PyMuPDF.
    with pymupdf.open(str(path)) as dokumen:

        jumlah_halaman = len(dokumen)

        # Batasi halaman jika diperlukan.
        if max_pages is not None:
            jumlah_halaman = min(jumlah_halaman, max_pages)

        konteks_teks = []
        konten_visual = []

        for i in range(jumlah_halaman):
            halaman = dokumen[i]

            # 1. Ekstrak teks.
            teks = halaman.get_text("text").strip()

            if teks:
                konteks_teks.append(f"Halaman {i + 1}:\n{teks}")

            # 2. Render halaman menjadi gambar.
            pix = halaman.get_pixmap(
                matrix=pymupdf.Matrix(1.5, 1.5),
                alpha=False,
            )

            gambar = base64.b64encode(pix.tobytes("png")).decode("utf-8")

            konten_visual.append({"type": "text", "text": f"Visual halaman {i + 1}:"})

            konten_visual.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{gambar}"},
                }
            )

    teks_pdf = "\n\n".join(konteks_teks)

    if not teks_pdf:
        teks_pdf = (
            "Tidak ada teks yang berhasil diekstrak. "
            "Gunakan gambar untuk membaca dokumen."
        )

    # 3. Gabungkan pertanyaan, teks, dan gambar.
    konten_user = [
        {
            "type": "text",
            "text": (
                f"PERTANYAAN:\n{pertanyaan}\n\n"
                f"TEKS DOKUMEN:\n{teks_pdf}\n\n"
                "jika pertanyaan tidak sesuai konteks"
                "nyatakan saya tidak tahu, dan jangan jelaskan apapun yang ada di dokumen"
                "kalau sesuai konteks, jawab berdasarkan keseluruhan teks dan gambar "
                "yang tersedia. Gunakan diagram, tabel, judul, "
                "dan tata letak sebagai konteks tambahan. "
                "Jangan mengarang informasi. Jika informasi "
                "tidak ditemukan, nyatakan dengan jelas."
            ),
        }
    ]

    konten_user.extend(konten_visual)

    # 4. Kirim ke model vision.
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Kamu adalah asisten yang memahami PDF "
                    "dan gambar. Jawab pertanyaan berdasarkan "
                    "bukti dari teks dan visual dokumen."
                ),
            },
            {"role": "user", "content": konten_user},
        ],
        max_tokens=1500,
    )

    return bersihkan_output(response.choices[0].message.content or "")


# Contoh penggunaan PDF
jawaban = analisis_dokumen(
    path="1f9e63d3-20e8-42cb-b676-fd985fdcbccc.jpeg",
    pertanyaan="berapa harga dari 1000 VP?",
)

print(jawaban)
