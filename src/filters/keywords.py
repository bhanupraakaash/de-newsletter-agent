"""Topic keywords. Grouped by topic so the ranker can weight them differently."""

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "Data Engineering": ["data engineering", "data engineer", "data pipeline", "data platform", "lakehouse", "data lake", "data warehouse"],
    "Databricks": ["databricks", "unity catalog", "dlt", "delta live tables", "lakeflow", "mosaic ai"],
    "Spark": ["spark", "pyspark", "spark sql", "structured streaming"],
    "Azure": ["azure", "microsoft fabric", "synapse", "azure data factory", "adf", "adls", "event hubs"],
    "SQL": ["sql", "query optimization", "window function"],
    "Delta Lake": ["delta lake", "delta table", "iceberg", "apache hudi", "parquet", "medallion"],
    "Airflow": ["airflow", "dagster", "prefect", "orchestration"],
    "Kafka": ["kafka", "event streaming", "flink", "change data capture", "cdc"],
    "Architecture": ["data architecture", "data mesh", "data modeling", "data modelling", "dimensional model"],
    "ETL/ELT": ["etl", "elt", "dbt", "data transformation", "data ingestion"],
    "Data Quality": ["data quality", "data observability", "data contract", "great expectations", "data lineage", "data governance"],
    "GenAI": ["generative ai", "genai", "llm", "rag", "vector database", "text-to-sql", "ai agent"],
}

# How central each topic is to a Data Engineer's week (multiplies keyword hits).
TOPIC_WEIGHTS: dict[str, float] = {
    "Data Engineering": 1.0, "Databricks": 1.0, "Spark": 1.0, "Azure": 0.9, "SQL": 0.7,
    "Delta Lake": 1.0, "Airflow": 0.9, "Kafka": 0.9, "Architecture": 0.9,
    "ETL/ELT": 0.9, "Data Quality": 0.9, "GenAI": 0.6,
}

ALL_KEYWORDS: list[str] = sorted({kw for kws in TOPIC_KEYWORDS.values() for kw in kws})
KEYWORD_TOPIC: dict[str, str] = {kw: topic for topic, kws in TOPIC_KEYWORDS.items() for kw in kws}
