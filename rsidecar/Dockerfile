# Stub image for the consensus-projection sidecar. The real ffanalytics
# pipeline (scored to RIP TIDE rules) arrives in ticket #8.
FROM r-base:4.4.2

WORKDIR /app
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
