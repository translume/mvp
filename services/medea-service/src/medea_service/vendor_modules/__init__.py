"""Namespace for selected, unchanged Medea source modules.

The service loads the verified upstream instructions, environment helpers,
DepMap parser and OpenScholar implementation here. This avoids executing
Medea's package initializer, which imports unrelated local-model workflows.
No dummy dependency or replacement scientific implementation is installed.
"""
