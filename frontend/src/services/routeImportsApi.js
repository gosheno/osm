const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/g, "") || "http://127.0.0.1:8000";

function normalizeApiError(data, fallback) {
  if (data?.error?.message) {
    const details = data.error.details ? ` ${data.error.details}` : "";
    return `${data.error.message}${details}`;
  }
  if (typeof data?.detail === "string") {
    return data.detail;
  }
  return fallback;
}

async function parseResponse(response, fallback) {
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(normalizeApiError(data, fallback));
  }
  return data;
}

export async function uploadRouteSheet(files) {
  const formData = new FormData();
  Array.from(files || []).forEach((file) => {
    formData.append("files", file);
  });

  const response = await fetch(`${API_BASE_URL}/api/imports/route-sheet`, {
    method: "POST",
    body: formData,
  });
  return parseResponse(response, "Не удалось загрузить маршрутный лист.");
}

export async function importLocalRouteSheet(routeName) {
  const params = new URLSearchParams();
  if (routeName) {
    params.set("route_name", routeName);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  const response = await fetch(`${API_BASE_URL}/api/imports/route-sheet/from-local${suffix}`, {
    method: "POST",
  });
  return parseResponse(response, "Не удалось загрузить локальные sample-файлы.");
}

export async function getRouteImport(importId) {
  const response = await fetch(`${API_BASE_URL}/api/imports/${importId}`);
  return parseResponse(response, "Не удалось получить результат OCR.");
}

export async function patchRouteImportItem(importId, itemId, payload) {
  const response = await fetch(`${API_BASE_URL}/api/imports/${importId}/items/${itemId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse(response, "Не удалось сохранить строку.");
}

export async function retryRouteImportItem(importId, itemId) {
  const response = await fetch(`${API_BASE_URL}/api/imports/${importId}/items/${itemId}/retry-geocode`, {
    method: "POST",
  });
  return parseResponse(response, "Не удалось повторить геокодирование.");
}

export async function confirmRouteImport(importId, payload) {
  const response = await fetch(`${API_BASE_URL}/api/imports/${importId}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse(response, "Не удалось построить маршрут из OCR-импорта.");
}
