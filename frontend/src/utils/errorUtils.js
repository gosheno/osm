function normalizeDetails(details) {
  if (details == null || typeof details === "string") {
    return details || null;
  }
  return JSON.stringify(details, null, 2);
}

export function normalizeApiError(error) {
  if (!error) {
    return {
      message: "Произошла неизвестная ошибка.",
      code: null,
      details: null,
      failed_addresses: [],
      warnings: [],
    };
  }

  const base = {
    message: "Произошла ошибка при запросе маршрута.",
    code: null,
    details: null,
    failed_addresses: [],
    warnings: [],
  };

  if (error.error) {
    return {
      message: error.error.message || base.message,
      code: error.error.code || null,
      details: normalizeDetails(error.error.details),
      failed_addresses: error.failed_addresses || [],
      warnings: error.warnings || [],
    };
  }

  if (error.detail) {
    return {
      ...base,
      message: Array.isArray(error.detail)
        ? "Проверьте корректность заполнения формы."
        : String(error.detail),
    };
  }

  return {
    ...base,
    message: String(error.message || error),
  };
}
