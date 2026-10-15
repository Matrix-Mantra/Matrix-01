FROM python:3.12-slim

# ffmpeg: converts browser voice recordings to WAV for Gemini.
# pango/harfbuzz: WeasyPrint needs them to lay out Nepali text in the PDF report.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libpango-1.0-0 libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

ENV PYTHONUNBUFFERED=1 PORT=8080
# One worker: the per-user daily limits live in memory (see README, "Scaling").
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1
