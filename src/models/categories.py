"""Newsletter categories. Order here is the order of sections in the newsletter."""

CATEGORIES: list[str] = [
    "Databricks & Spark",
    "Azure Data Engineering",
    "Data & AI",
    "Tools / Open Source",
    "Architecture & Practices",
]

# Used only by the no-LLM fallback, to map keyword topics onto categories.
TOPIC_TO_CATEGORY: dict[str, str] = {
    "Databricks": "Databricks & Spark",
    "Spark": "Databricks & Spark",
    "Delta Lake": "Databricks & Spark",
    "Azure": "Azure Data Engineering",
    "GenAI": "Data & AI",
    "Airflow": "Tools / Open Source",
    "Kafka": "Tools / Open Source",
    "ETL/ELT": "Tools / Open Source",
    "SQL": "Tools / Open Source",
    "Data Engineering": "Architecture & Practices",
    "Architecture": "Architecture & Practices",
    "Data Quality": "Architecture & Practices",
}
