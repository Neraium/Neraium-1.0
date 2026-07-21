FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    BACKEND_HOST=0.0.0.0 \
    BACKEND_PORT=8080

WORKDIR /app

COPY requirements.txt .

RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements.txt && \
    addgroup --system --gid 10001 neraium && \
    adduser --system --uid 10001 --ingroup neraium --home /nonexistent --no-create-home neraium

COPY api ./api
COPY app ./app
COPY archives ./archives
COPY audit ./audit
COPY behavior_science ./behavior_science
COPY benchmarking ./benchmarking
COPY case_studies ./case_studies
COPY certification ./certification
COPY cognition ./cognition
COPY cognition_graph ./cognition_graph
COPY cross_domain ./cross_domain
COPY cultivation ./cultivation
COPY datasets ./datasets
COPY db ./db
COPY digital_twin ./digital_twin
COPY domain_packs ./domain_packs
COPY engines ./engines
COPY evidence ./evidence
COPY exchange ./exchange
COPY explainability ./explainability
COPY explanations ./explanations
COPY federation ./federation
COPY governance ./governance
COPY human_factors ./human_factors
COPY integrations ./integrations
COPY interoperability ./interoperability
COPY laboratory ./laboratory
COPY mathematics ./mathematics
COPY ontology ./ontology
COPY primitives ./primitives
COPY reasoning ./reasoning
COPY replay ./replay
COPY research ./research
COPY search ./search
COPY sii_reference_architecture ./sii_reference_architecture
COPY sii_standard ./sii_standard
COPY simulation ./simulation
COPY training ./training
COPY trust ./trust
COPY validation ./validation
COPY runtime/runtime_contracts.py ./runtime/runtime_contracts.py
COPY runtime/runtime_state.py ./runtime/runtime_state.py
COPY runtime/sii_runtime.py ./runtime/sii_runtime.py

RUN mkdir -p /app/app/runtime /mnt/neraium-runtime /var/log/neraium && \
    chown -R neraium:neraium /app/app/runtime /mnt/neraium-runtime /var/log/neraium

EXPOSE 8080

STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=5).read()" || exit 1

USER neraium

CMD ["python", "-m", "app.entrypoint"]
