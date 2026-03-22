"""
Root-level conftest.py for pytest.

Injects mock NetBox modules into sys.modules before pytest collects tests,
allowing tests to run without a NetBox environment.
"""
import sys
from types import ModuleType
from unittest.mock import MagicMock


def _inject_mock_netbox():
    """
    Inject dummy NetBox modules only when running outside a NetBox environment
    (i.e., 'netbox' is not already in sys.modules).
    Does nothing inside a Docker container with real NetBox installed.
    """
    if 'netbox' in sys.modules:
        return

    # --- netbox.plugins.PluginConfig ---
    fake_netbox = ModuleType('netbox')
    fake_plugins = ModuleType('netbox.plugins')

    class _FakePluginConfig:
        name = ''
        verbose_name = ''
        version = ''
        description = ''
        min_version = ''
        max_version = ''
        def __init_subclass__(cls, **kwargs):
            pass
        def ready(self):
            pass

    fake_plugins.PluginConfig = _FakePluginConfig
    fake_netbox.plugins = fake_plugins
    sys.modules['netbox'] = fake_netbox
    sys.modules['netbox.plugins'] = fake_plugins

    # --- netbox.models.NetBoxModel ---
    fake_netbox_models = ModuleType('netbox.models')
    fake_netbox_models.NetBoxModel = type('NetBoxModel', (), {})
    sys.modules['netbox.models'] = fake_netbox_models

    # --- dcim.models.Device ---
    fake_dcim = ModuleType('dcim')
    fake_dcim_models = ModuleType('dcim.models')
    fake_dcim_models.Device = type('Device', (), {})
    fake_dcim.models = fake_dcim_models
    sys.modules['dcim'] = fake_dcim
    sys.modules['dcim.models'] = fake_dcim_models

    # --- Django core (minimal mock) ---
    for mod_name in [
        'django',
        'django.db',
        'django.db.models',
        'django.urls',
        'django.utils',
        'django.utils.translation',
    ]:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = MagicMock()


_inject_mock_netbox()
