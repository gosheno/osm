# Known POI Import

The known POI importer is a manual, one-time maintenance script for loading local chain-store points from an offline `.osm.pbf` extract. It does not call public APIs. Optional Nominatim enrichment must point at a local Nominatim instance.

## Database

Apply the migration before the first import:

```powershell
Get-Content -Raw backend\migrations\005_known_pois.sql | docker compose exec -T db psql -U osm_user -d osm_routes
```

The migration creates:

- `known_pois`
- `poi_brand_aliases`
- `poi_import_runs`

## Configuration

Chain aliases and the regional bounding box live in `backend/app/config/poi_chains.yml`.

The initial configured chains are:

- Пятёрочка
- Семишагофф
- Лента
- ОКЕЙ
- Азбука вкуса
- ВкусВилл

## Import

Run a dry report first:

```powershell
$env:PYTHONPATH='backend'
python -m app.scripts.import_known_pois `
  --pbf data\spb-latest.osm.pbf `
  --db-url postgresql://osm_user:osm_password@localhost:5432/osm_routes `
  --dry-run `
  --export-report reports\known_pois
```

Write to the database:

```powershell
$env:PYTHONPATH='backend'
python -m app.scripts.import_known_pois `
  --pbf data\spb-latest.osm.pbf `
  --db-url postgresql://osm_user:osm_password@localhost:5432/osm_routes `
  --update-existing `
  --export-report reports\known_pois
```

Optional local Nominatim enrichment:

```powershell
python -m app.scripts.import_known_pois `
  --pbf data\spb-latest.osm.pbf `
  --db-url postgresql://osm_user:osm_password@localhost:5432/osm_routes `
  --enrich-with-nominatim `
  --nominatim-url http://127.0.0.1:8080 `
  --update-existing
```

The script refuses `nominatim.openstreetmap.org` for enrichment.

## Search API

Known POIs can be searched through:

```text
GET /api/pois/search?q=VkusVill&lat=59.93&lon=30.33&radius_m=1000&limit=10
```

The address geocoder also checks `known_pois` before ordinary geocoding and auto-accepts only high-confidence, non-ambiguous matches.
