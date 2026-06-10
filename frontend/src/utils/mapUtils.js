export const DEFAULT_MAP_CENTER = [59.9398, 30.3141];

export function toLeafletLatLng(point) {
  return [point.latitude, point.longitude];
}

export function orderedPointsToLatLngs(points) {
  return points.map(toLeafletLatLng);
}
