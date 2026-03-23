from netbox.plugins import PluginTemplateExtension


class DeviceManagedPDUButton(PluginTemplateExtension):
    models = ["dcim.device"]

    def buttons(self):
        device = self.context["object"]
        try:
            pdu = device.managed_pdu
        except Exception:
            return ""
        return self.render(
            "netbox_pdu_plugin/inc/device_pdu_button.html",
            extra_context={"pdu": pdu},
        )

    def right_page(self):
        device = self.context["object"]
        outlets = list(device.pdu_outlets.select_related("managed_pdu").order_by("managed_pdu", "outlet_number"))
        if not outlets:
            return ""
        return self.render(
            "netbox_pdu_plugin/inc/device_pdu_outlets.html",
            extra_context={"pdu_outlets": outlets},
        )


template_extensions = [DeviceManagedPDUButton]
