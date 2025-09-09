FROM python:3.11

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app


# Install system dependencies
RUN apt-get update \
	&& apt-get install -y ffmpeg \

COPY requirements.txt /app/
RUN pip install -r requirements.txt

COPY . /app/

# Copy and make entrypoint script executable
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

CMD ["/app/entrypoint.sh"]