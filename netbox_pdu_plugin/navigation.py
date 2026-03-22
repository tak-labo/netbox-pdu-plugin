from django.utils.translation import gettext_lazy as _
from netbox.plugins import PluginMenu, PluginMenuButton, PluginMenuItem

managedpdu_buttons = [
    PluginMenuButton(
        link='plugins:netbox_pdu_plugin:managedpdu_add',
        title=_('Add'),
        icon_class='mdi mdi-plus-thick',
        permissions=['netbox_pdu_plugin.add_managedpdu'],
    )
]

pduoutlet_buttons = [
    PluginMenuButton(
        link='plugins:netbox_pdu_plugin:pduoutlet_add',
        title=_('Add'),
        icon_class='mdi mdi-plus-thick',
        permissions=['netbox_pdu_plugin.add_pduoutlet'],
    )
]

managedpdu_item = PluginMenuItem(
    link='plugins:netbox_pdu_plugin:managedpdu_list',
    link_text=_('Managed PDUs'),
    permissions=['netbox_pdu_plugin.view_managedpdu'],
    buttons=managedpdu_buttons,
)

pduoutlet_item = PluginMenuItem(
    link='plugins:netbox_pdu_plugin:pduoutlet_list',
    link_text=_('PDU Outlets'),
    permissions=['netbox_pdu_plugin.view_pduoutlet'],
    buttons=pduoutlet_buttons,
)

pduinlet_buttons = [
    PluginMenuButton(
        link='plugins:netbox_pdu_plugin:pduinlet_list',
        title=_('View'),
        icon_class='mdi mdi-format-list-bulleted',
        permissions=['netbox_pdu_plugin.view_pduinlet'],
    )
]

pduinlet_item = PluginMenuItem(
    link='plugins:netbox_pdu_plugin:pduinlet_list',
    link_text=_('PDU Inlets'),
    permissions=['netbox_pdu_plugin.view_pduinlet'],
    buttons=pduinlet_buttons,
)

menu = PluginMenu(
    label='PDU Management',
    groups=(
        ('PDUs', (managedpdu_item,)),
        ('Outlets', (pduoutlet_item,)),
        ('Inlets', (pduinlet_item,)),
    ),
    icon_class='mdi mdi-power-socket',
)
