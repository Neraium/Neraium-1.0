FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend \
    BACKEND_HOST=0.0.0.0 \
    BACKEND_PORT=8080

WORKDIR /app

COPY backend/requirements.txt .

RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -r requirements.txt && \
    addgroup --system --gid 10001 neraium && \
    adduser --system --uid 10001 --ingroup neraium --home /nonexistent --no-create-home neraium

COPY backend/api ./backend/api
COPY backend/app ./backend/app
COPY backend/archives ./backend/archives
COPY backend/audit ./backend/audit
COPY backend/behavior_science ./backend/behavior_science
COPY backend/benchmarking ./backend/benchmarking
COPY backend/case_studies ./backend/case_studies
COPY backend/certification ./backend/certification
COPY backend/cognition ./backend/cognition
COPY backend/cognition_graph ./backend/cognition_graph
COPY backend/cross_domain ./backend/cross_domain
COPY backend/cultivation ./backend/cultivation
COPY backend/datasets ./backend/datasets
COPY backend/db ./backend/db
COPY backend/digital_twin ./backend/digital_twin
COPY backend/domain_packs ./backend/domain_packs
COPY backend/engines ./backend/engines
COPY backend/evidence ./backend/evidence
COPY backend/exchange ./backend/exchange
COPY backend/explainability ./backend/explainability
COPY backend/explanations ./backend/explanations
COPY backend/federation ./backend/federation
COPY backend/governance ./backend/governance
COPY backend/human_factors ./backend/human_factors
COPY backend/integrations ./backend/integrations
COPY backend/interoperability ./backend/interoperability
COPY backend/laboratory ./backend/laboratory
COPY backend/mathematics ./backend/mathematics
COPY backend/ontology ./backend/ontology
COPY backend/primitives ./backend/primitives
COPY backend/reasoning ./backend/reasoning
COPY backend/replay ./backend/replay
COPY backend/research ./backend/research
COPY backend/search ./backend/search
COPY backend/sii_reference_architecture ./backend/sii_reference_architecture
COPY backend/sii_standard ./backend/sii_standard
COPY backend/simulation ./backend/simulation
COPY backend/training ./backend/training
COPY backend/trust ./backend/trust
COPY backend/validation ./backend/validation
COPY backend/runtime/runtime_contracts.py ./backend/runtime/runtime_contracts.py
COPY backend/runtime/runtime_state.py ./backend/runtime/runtime_state.py
COPY backend/runtime/sii_runtime.py ./backend/runtime/sii_runtime.py

RUN mkdir -p /app/backend/app/runtime /mnt/neraium-runtime /var/log/neraium && \
    chown -R neraium:neraium /app/backend/app/runtime /mnt/neraium-runtime /var/log/neraium

WORKDIR /app/backend

EXPOSE 8080

STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=5).read()" || exit 1

USER neraium

CMD ["python", "-m", "app.entrypoint"]
