import importlib

yield_service = importlib.import_module("app.services.yield")
calculate_recommended_price = yield_service.calculate_recommended_price

__all__ = ["calculate_recommended_price"]
