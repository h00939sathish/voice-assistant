"""
Compatibility shim — re-exports OperatorDashboard from gui/.

Import as:
    from assistant.operator_dashboard import OperatorDashboard
"""

from gui.operator_dashboard import OperatorDashboard

__all__ = ["OperatorDashboard"]
