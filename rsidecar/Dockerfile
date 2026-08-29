# The consensus-projection sidecar: runs ffanalytics once per invocation and
# drops a raw stat-projection payload for the backend to re-score to RIP TIDE
# rules (spec issue #8; docs/adr/0005). Not built or run in CI — the backend is
# tested against recorded payload fixtures.
FROM rocker/r-ver:4.4.2

# System libraries ffanalytics's scraping stack needs (xml2, curl, openssl).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxml2-dev libcurl4-openssl-dev libssl-dev libgit2-dev \
    && rm -rf /var/lib/apt/lists/*

RUN R -e "install.packages(c('remotes','jsonlite'), repos='https://cloud.r-project.org')" \
    && R -e "remotes::install_github('FantasyFootballAnalytics/ffanalytics', upgrade='never')"

WORKDIR /app
COPY entrypoint.sh run.R /app/
RUN chmod +x /app/entrypoint.sh

ENV DEADPARROTS_DATA_DIR=/data

ENTRYPOINT ["/app/entrypoint.sh"]
