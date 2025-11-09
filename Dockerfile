FROM python:3.11

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app


# Install system dependencies
RUN apt-get update \
	&& apt-get install -y ffmpeg \
	&& apt-get install -y apturl

RUN pip install gunicorn
COPY requirements.txt /app/
RUN pip install -r requirements.txt

COPY . /app/

# Copy and make entrypoint scripts executable
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

COPY celery_beat_endpoint.sh /app/celery_beat_endpoint.sh
RUN chmod +x /app/celery_beat_endpoint.sh

COPY celery_worker_endpoint.sh /app/celery_worker_endpoint.sh
RUN chmod +x /app/celery_worker_endpoint.sh

EXPOSE 8000

CMD ["/app/entrypoint.sh"]