from app.integrations.aws import AWSConnector
from app.integrations.base import Connector
from app.integrations.github import GitHubConnector

REGISTRY: dict[str, type[Connector]] = {c.provider: c for c in (AWSConnector, GitHubConnector)}
