export function formatDistance(meters) {
  if (meters == null || Number.isNaN(meters)) {
    return "-";
  }
  if (meters < 1000) {
    return `${Math.round(meters)} м`;
  }
  const km = meters / 1000;
  return `${km.toFixed(1).replace('.', ',')} км`;
}

export function formatDuration(seconds) {
  if (seconds == null || Number.isNaN(seconds)) {
    return "-";
  }
  const totalSeconds = Math.round(seconds);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.round((totalSeconds % 3600) / 60);

  if (hours === 0) {
    return `${minutes} мин`;
  }
  if (minutes === 0) {
    return `${hours} ч`;
  }
  return `${hours} ч ${minutes} мин`;
}

export function formatCoordinate(value) {
  if (value == null || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(6);
}

export function formatAddressLabel(point) {
  return point.address?.original_address || point.address?.normalized_address || point.label || "-";
}
