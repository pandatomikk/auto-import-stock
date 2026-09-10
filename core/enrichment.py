"""Optional description enrichment provided by a trusted local adapter."""
from .profiles import load_adapter


class SupplierDescriptions:
    def __init__(self, settings):
        self.provider = None
        self.records = []
        if settings.get('enabled'):
            if not settings.get('adapter'):
                raise ValueError('Un adaptateur local est requis pour enrichir les descriptions.')
            self.provider = load_adapter(settings['adapter']).SupplierDescriptions(settings)
            self.records = self.provider.records

    def get(self, values):
        return self.provider.get(values) if self.provider else None
