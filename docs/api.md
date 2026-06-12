## Geocoding context

`POST /api/routes/optimize` and `POST /api/addresses/geocode` accept an optional
search context for address geocoding.

Use a predefined context:

```json
{
  "geocoding_context": {
    "type": "spb_lenobl",
    "bounded": false
  }
}
```

Use a user-provided settlement or district:

```json
{
  "geocoding_area": "Кудрово"
}
```

Supported MVP context types:

- `default_spb`: Saint Petersburg, soft Nominatim viewbox.
- `spb_lenobl`: Saint Petersburg plus nearby Leningrad Oblast, soft viewbox.
- `district` / `custom_area`: resolved from `label` or `geocoding_area`.

Responses include diagnostic fields such as `geocoding_query`,
`geocoding_score`, `geocoding_context_label`, and `distance_to_context_m`.
Addresses with `geocoding_status = "ambiguous"` are returned as failed
addresses for review instead of being silently optimized into the route.
