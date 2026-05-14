FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY api ./api
COPY audit ./audit
COPY benchmarking ./benchmarking
COPY case_studies ./case_studies
COPY certification ./certification
COPY cognition ./cognition
COPY cognition_graph ./cognition_graph
COPY cross_domain ./cross_domain
COPY datasets ./datasets
COPY digital_twin ./digital_twin
COPY domain_packs ./domain_packs
COPY evidence ./evidence
COPY exchange ./exchange
COPY federation ./federation
COPY engines ./engines
COPY explanations ./explanations
COPY governance ./governance
COPY human_factors ./human_factors
COPY ontology ./ontology
COPY replay ./replay
COPY search ./search
COPY sii_reference_architecture ./sii_reference_architecture
COPY sii_standard ./sii_standard
COPY simulation ./simulation
COPY training ./training
COPY trust ./trust
COPY validation ./validation

EXPOSE 80

CMD ["sh", "-c", "python -m uvicorn app.main:app --host ${BACKEND_HOST:-0.0.0.0} --port ${BACKEND_PORT:-80}"]
