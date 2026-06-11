function toFiniteNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function formatDistance(meters) {
  const value = toFiniteNumber(meters);
  if (value == null) {
    return "-";
  }
  if (value < 1000) {
    return `${Math.round(value)} м`;
  }
  const km = value / 1000;
  return `${km.toFixed(1).replace('.', ',')} км`;
}

export function formatDuration(seconds) {
  const value = toFiniteNumber(seconds);
  if (value == null) {
    return "-";
  }
  const totalSeconds = Math.round(value);
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
  const number = toFiniteNumber(value);
  if (number == null) {
    return "-";
  }
  return number.toFixed(6);
}

export function formatAddressLabel(point) {
  return (
    point.address?.original_address ||
    point.address?.input_address ||
    point.address?.normalized_address ||
    point.input_address ||
    point.original_address ||
    point.label ||
    "-"
  );
}
