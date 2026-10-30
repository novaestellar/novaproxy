FROM node:20-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt requirements-browser.txt ./

# Headless Chromium is optional and costs ~1.5 GB with its system libraries.
# The default image is the console + gateway; only pass --build-arg
# WITH_BROWSER=1 if you actually use the signup-gated sources.
ARG WITH_BROWSER=0
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ "$WITH_BROWSER" = "1" ]; then \
      pip install --no-cache-dir -r requirements-browser.txt \
      && playwright install --with-deps chromium ; \
    fi

COPY . .
COPY --from=web /web/dist ./web/dist

EXPOSE 12000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "12000"]
