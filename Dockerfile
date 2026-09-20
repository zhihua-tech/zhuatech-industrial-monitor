FROM python:3.12-alpine
WORKDIR /app
COPY . .
RUN python -m unittest discover -s tests -v && mkdir -p /app/data
RUN adduser -D -u 10001 app && chown -R app /app
USER app
EXPOSE 18084
CMD ["python", "-m", "app.server"]
