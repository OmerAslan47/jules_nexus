import sys
import os
import types

# Ensure core and core.paths can be imported cleanly across tests
nexus_root = os.path.abspath(os.path.join(os.path.dirname(__file__), 'jules_nexus'))

if 'core' not in sys.modules:
    core_mod = types.ModuleType('core')
    paths_mod = types.ModuleType('core.paths')
    paths_mod.NEXUS_ROOT = nexus_root
    core_mod.paths = paths_mod

    # Add core.plugin_manager stub if needed
    plugin_mod = types.ModuleType('core.plugin_manager')
    def nexus_tool(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    plugin_mod.nexus_tool = nexus_tool
    core_mod.plugin_manager = plugin_mod

    sys.modules['core'] = core_mod
    sys.modules['core.paths'] = paths_mod
    sys.modules['core.plugin_manager'] = plugin_mod
