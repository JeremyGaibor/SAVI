# syntax=docker/dockerfile:1

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# collectstatic requiere inicializar Django, pero no utiliza la clave de firma.
# El valor temporal solo existe durante esta instrucción de construcción.
RUN DJANGO_SECRET_KEY=build-only-not-for-runtime python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "assistant.wsgi:application", "--bind", "0.0.0.0:8000", "--timeout", "180"]
