from app.core.config import settings
from app.clients.nominatim_client import NominatimClient
from app.clients.opencage_client import OpenCageClient


def get_geocoder():
    provider = settings.GEOCODER_PROVIDER.lower().strip()

    if provider == "opencage":
        return OpenCageClient()

    if provider == "nominatim":
        return NominatimClient()

    raise ValueError(f"Unsupported geocoder provider: {settings.GEOCODER_PROVIDER}")
