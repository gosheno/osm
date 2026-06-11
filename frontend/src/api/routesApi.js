const API_BASE_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/g, "") || "http://127.0.0.1:8000";

function normalizeDetail(detail) {
  if (Array.isArray(detail)) {
    return "Проверьте заполнение формы.";
  }
  if (typeof detail === "string") {
    return detail;
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return "Произошла ошибка на backend.";
}

export async function optimizeRoute(payload) {
  const url = `${API_BASE_URL}/api/routes/optimize`;
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json().catch(() => null);

    if (!response.ok) {
      if (data?.error) {
        throw data;
      }

      const message = data?.detail ? normalizeDetail(data.detail) : "Backend недоступен. Проверьте, запущен ли docker compose.";
      throw new Error(message);
    }

    return data;
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error("Backend недоступен. Проверьте, запущен ли docker compose.");
    }
    throw error;
  }
}
