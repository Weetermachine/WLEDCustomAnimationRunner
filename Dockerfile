FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    DB_PATH=/data/wled.db \
    TZ=America/Denver

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py animator.py scheduler.py database.py auth.py strip_colors.py reset_password.py ./
COPY static ./static

EXPOSE 8093

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8093", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
