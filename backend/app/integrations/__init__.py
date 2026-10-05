from app.integrations.aws import AWSConnector
from app.integrations.azure import AzureConnector
from app.integrations.base import Connector
from app.integrations.darwinbox import DarwinboxConnector
from app.integrations.devices import IntuneConnector, JamfConnector
from app.integrations.gcp import GCPConnector
from app.integrations.github import GitHubConnector
from app.integrations.gitlab import GitLabConnector
from app.integrations.google_workspace import GoogleWorkspaceConnector
from app.integrations.jira import JiraConnector
from app.integrations.keka import KekaConnector
from app.integrations.microsoft365 import Microsoft365Connector
from app.integrations.okta import OktaConnector

REGISTRY: dict[str, type[Connector]] = {
    c.provider: c
    for c in (GoogleWorkspaceConnector, Microsoft365Connector, OktaConnector, AWSConnector, AzureConnector,
              GCPConnector, GitHubConnector, GitLabConnector, IntuneConnector, JamfConnector, KekaConnector,
              DarwinboxConnector, JiraConnector)
}
