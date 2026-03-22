"""
NetBox PDU Plugin

Plugin configuration for NetBox PDU Plugin.

For a complete list of PluginConfig attributes, see:
https://docs.netbox.dev/en/stable/plugins/development/#pluginconfig-attributes
"""

__author__ = "Takahiro Nagafuchi"
__email__ = "github@tak-lab.com"
__version__ = "0.1.0"


from netbox.plugins import PluginConfig


class PduConfig(PluginConfig):
    name = "netbox_pdu_plugin"
    verbose_name = "NetBox PDU Plugin"
    description = "NetBox plugin for Managed PDUs."
    author = "Takahiro Nagafuchi"
    author_email = "github@tak-lab.com"
    version = __version__
    base_url = "pdu"
    min_version = "4.5.0"
    max_version = "4.5.99"
    graphql_schema = "graphql.schema"
    queues = ["default"]


config = PduConfig
