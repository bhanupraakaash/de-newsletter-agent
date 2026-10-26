"""Trusted feed list. Add or remove feeds here; no other code changes needed."""
from pydantic import BaseModel


class FeedConfig(BaseModel):
    name: str
    url: str


FEEDS: list[FeedConfig] = [
    # Blogs / newsletters
    FeedConfig(name="Databricks Blog", url="https://www.databricks.com/feed"),
    FeedConfig(name="Azure Blog", url="https://azure.microsoft.com/en-us/blog/feed/"),
    FeedConfig(name="Microsoft Fabric Blog", url="https://blog.fabric.microsoft.com/en-us/blog/feed/"),
    FeedConfig(name="Confluent Blog", url="https://www.confluent.io/blog/feed/"),
    FeedConfig(name="Data Engineering Weekly", url="https://www.dataengineeringweekly.com/feed"),
    FeedConfig(name="Seattle Data Guy", url="https://seattledataguy.substack.com/feed"),
    FeedConfig(name="Netflix Tech Blog", url="https://netflixtechblog.com/feed"),
    FeedConfig(name="dbt Blog", url="https://docs.getdbt.com/blog/rss.xml"),
    # GitHub releases (Atom)
    FeedConfig(name="Apache Spark Releases", url="https://github.com/apache/spark/releases.atom"),
    FeedConfig(name="Delta Lake Releases", url="https://github.com/delta-io/delta/releases.atom"),
    FeedConfig(name="Apache Airflow Releases", url="https://github.com/apache/airflow/releases.atom"),
    FeedConfig(name="Apache Kafka Releases", url="https://github.com/apache/kafka/releases.atom"),
]
