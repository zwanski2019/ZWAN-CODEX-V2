FROM golang:1.23-alpine AS go-builder

RUN go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest && \
    go install github.com/projectdiscovery/httpx/cmd/httpx@latest && \
    go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest && \
    go install github.com/projectdiscovery/katana/cmd/katana@latest && \
    go install github.com/projectdiscovery/ffuf/v2/cmd/ffuf@latest && \
    go install github.com/projectdiscovery/interactsh/cmd/interactsh-client@latest

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget git nmap masscan jq \
    && rm -rf /var/lib/apt/lists/*

COPY --from=go-builder /go/bin/subfinder /usr/local/bin/
COPY --from=go-builder /go/bin/httpx /usr/local/bin/
COPY --from=go-builder /go/bin/nuclei /usr/local/bin/
COPY --from=go-builder /go/bin/katana /usr/local/bin/
COPY --from=go-builder /go/bin/ffuf /usr/local/bin/
COPY --from=go-builder /go/bin/interactsh-client /usr/local/bin/

RUN pip install --no-cache-dir mitmproxy playwright && \
    playwright install chromium --with-deps

CMD ["bash"]
