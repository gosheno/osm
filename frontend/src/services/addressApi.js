const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/g, "") || "http://127.0.0.1:8000";

function normalizeDetail(detail, fallback) {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return fallback;
  }
  if (detail && typeof detail === "object") {
    return detail.error || detail.message || JSON.stringify(detail);
  }
  return fallback;
}

async function requestJson(url, options = {}, fallbackMessage) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (_error) {
    throw new Error("Address search service is temporarily unavailable.");
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(normalizeDetail(data?.detail, fallbackMessage));
  }
  return data;
}

export async function suggestAddresses(query, options = {}) {
  const params = new URLSearchParams({
    query,
    limit: String(options.limit ?? 5),
    lang: options.lang ?? "ru",
  });

  if (options.bounded != null) {
    params.set("bounded", String(Boolean(options.bounded)));
  }
  if (options.viewbox) {
    params.set("viewbox", options.viewbox);
  }
  if (options.contextCity) {
    params.set("context_city", options.contextCity);
  }
  if (options.contextRegion) {
    params.set("context_region", options.contextRegion);
  }

  return requestJson(
    `${API_BASE_URL}/api/addresses/suggest?${params.toString()}`,
    {},
    "No addresses found. Please check the spelling or add city/region.",
  );
}

export async function confirmAddress(payload) {
  return requestJson(
    `${API_BASE_URL}/api/addresses/confirm`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
    "Could not save the selected address.",
  );
}

export async function checkNominatimHealth() {
  return requestJson(
    `${API_BASE_URL}/api/health/nominatim`,
    {},
    "Address search service is temporarily unavailable.",
  );
}
