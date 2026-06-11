import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.clients.opencage_client import (
    OpenCageClient,
    OpenCageConfigError,
    OpenCageUnexpectedResponseError,
)


@pytest.fixture
def mock_settings():
    """Fixture to mock settings for OpenCage client tests."""
    with patch("app.clients.opencage_client.settings") as mock:
        mock.OPENCAGE_API_KEY = "test_api_key_12345678901234567890"
        mock.OPENCAGE_BASE_URL = "https://api.opencagedata.com/geocode/v1"
        mock.OPENCAGE_LANGUAGE = "ru"
        mock.OPENCAGE_COUNTRYCODE = "ru"
        mock.OPENCAGE_LIMIT = 3
        mock.OPENCAGE_NO_ANNOTATIONS = True
        mock.OPENCAGE_NO_RECORD = True
        yield mock


def test_opencage_client_missing_api_key():
    """Test that OpenCageClient raises error when API key is not set."""
    with patch("app.clients.opencage_client.settings") as mock_settings:
        mock_settings.OPENCAGE_API_KEY = None
        
        with pytest.raises(OpenCageConfigError, match="OPENCAGE_API_KEY is not set"):
            OpenCageClient()


def test_opencage_client_init(mock_settings):
    """Test that OpenCageClient initializes correctly with valid settings."""
    client = OpenCageClient()
    
    assert client.base_url == "https://api.opencagedata.com/geocode/v1"


@pytest.mark.asyncio
async def test_opencage_search_success(mock_settings):
    """Test successful geocoding request returns correct candidates."""
    client = OpenCageClient()
    
    mock_response = {
        "status": {"code": 200, "message": "OK"},
        "results": [
            {
                "geometry": {"lat": 55.7558, "lng": 37.6173},
                "formatted": "Москва, Россия",
                "confidence": 9,
            }
        ],
    }
    
    mock_http_response = MagicMock()
    mock_http_response.status_code = 200
    mock_http_response.json = MagicMock(return_value=mock_response)
    
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_http_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    with patch("httpx.AsyncClient", return_value=mock_client):
        results = await client.search("Москва")
    
    assert len(results) == 1
    assert results[0].latitude == 55.7558
    assert results[0].longitude == 37.6173
    assert results[0].display_name == "Москва, Россия"
    assert results[0].confidence == 9


@pytest.mark.asyncio
async def test_opencage_search_empty_results(mock_settings):
    """Test that empty results return empty list."""
    client = OpenCageClient()
    
    mock_response = {
        "status": {"code": 200, "message": "OK"},
        "results": [],
    }
    
    mock_http_response = MagicMock()
    mock_http_response.status_code = 200
    mock_http_response.json = MagicMock(return_value=mock_response)
    
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_http_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    with patch("httpx.AsyncClient", return_value=mock_client):
        results = await client.search("NOWHERE-INTERESTING")
    
    assert results == []


@pytest.mark.asyncio
async def test_opencage_search_error_response(mock_settings):
    """Test that error status code raises exception."""
    client = OpenCageClient()
    
    mock_response = {
        "status": {"code": 401, "message": "Invalid API key"},
        "results": [],
    }
    
    mock_http_response = MagicMock()
    mock_http_response.status_code = 401
    mock_http_response.json = MagicMock(return_value=mock_response)
    
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_http_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(OpenCageUnexpectedResponseError, match="Invalid API key"):
            await client.search("test")


@pytest.mark.asyncio
async def test_opencage_search_invalid_results_format(mock_settings):
    """Test that invalid results format raises exception."""
    client = OpenCageClient()
    
    mock_response = {
        "status": {"code": 200, "message": "OK"},
        "results": "invalid",  # Should be a list
    }
    
    mock_http_response = MagicMock()
    mock_http_response.status_code = 200
    mock_http_response.json = MagicMock(return_value=mock_response)
    
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_http_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    with patch("httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(OpenCageUnexpectedResponseError, match="invalid results"):
            await client.search("test")


@pytest.mark.asyncio
async def test_opencage_search_missing_geometry(mock_settings):
    """Test that items without lat/lng are skipped."""
    client = OpenCageClient()
    
    mock_response = {
        "status": {"code": 200, "message": "OK"},
        "results": [
            {
                "geometry": {"lat": 55.7558},  # Missing lng
                "formatted": "Incomplete result",
                "confidence": 5,
            },
            {
                "geometry": {"lat": 56.0, "lng": 37.0},
                "formatted": "Valid result",
                "confidence": 8,
            },
        ],
    }
    
    mock_http_response = MagicMock()
    mock_http_response.status_code = 200
    mock_http_response.json = MagicMock(return_value=mock_response)
    
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_http_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    with patch("httpx.AsyncClient", return_value=mock_client):
        results = await client.search("test")
    
    # Only the second result should be returned
    assert len(results) == 1
    assert results[0].latitude == 56.0
    assert results[0].longitude == 37.0


@pytest.mark.asyncio
async def test_opencage_search_with_limit(mock_settings):
    """Test that custom limit parameter is passed correctly."""
    client = OpenCageClient()
    
    mock_response = {
        "status": {"code": 200, "message": "OK"},
        "results": [
            {
                "geometry": {"lat": 55.0, "lng": 37.0},
                "formatted": "Result",
                "confidence": 8,
            },
        ],
    }
    
    mock_http_response = MagicMock()
    mock_http_response.status_code = 200
    mock_http_response.json = MagicMock(return_value=mock_response)
    
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_http_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    with patch("httpx.AsyncClient", return_value=mock_client):
        results = await client.search("test", limit=5)
    
    assert len(results) == 1


@pytest.mark.asyncio
async def test_opencage_search_confidence_none(mock_settings):
    """Test handling of missing confidence field."""
    client = OpenCageClient()
    
    mock_response = {
        "status": {"code": 200, "message": "OK"},
        "results": [
            {
                "geometry": {"lat": 55.0, "lng": 37.0},
                "formatted": "Result without confidence",
                # No confidence field
            },
        ],
    }
    
    mock_http_response = MagicMock()
    mock_http_response.status_code = 200
    mock_http_response.json = MagicMock(return_value=mock_response)
    
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_http_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    
    with patch("httpx.AsyncClient", return_value=mock_client):
        results = await client.search("test")
    
    assert len(results) == 1
    assert results[0].confidence is None
