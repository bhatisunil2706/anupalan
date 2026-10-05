from app.integrations.aws import AWSConnector
from app.integrations.base import Connector
from app.integrations.github import GitHubConnector
from app.integrations.google_workspace import GoogleWorkspaceConnector
from app.integrations.keka import KekaConnector
from app.integrations.microsoft365 import Microsoft365Connector

REGISTRY: dict[str, type[Connector]] = {
    c.provider: c
    for c in (GoogleWorkspaceConnector, Microsoft365Connector, AWSConnector, GitHubConnector, KekaConnector)
}
