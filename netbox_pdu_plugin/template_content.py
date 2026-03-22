from netbox.plugins import PluginTemplateExtension


class DeviceManagedPDUButton(PluginTemplateExtension):
    models = ['dcim.device']

    def buttons(self):
        device = self.context['object']
        try:
            pdu = device.managed_pdu
        except Exception:
            return ''
        return self.render(
            'netbox_pdu_plugin/inc/device_pdu_button.html',
            extra_context={'pdu': pdu},
        )


template_extensions = [DeviceManagedPDUButton]
