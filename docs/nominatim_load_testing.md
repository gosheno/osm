# Нагрузочное тестирование Nominatim-интеграции

Этот прогон нужен после подключения локального Nominatim, чтобы увидеть нагрузку на backend, PostgreSQL, Nominatim, OSRM, Docker и хост.

## Запуск локального Nominatim

1. Создать env-файл:

```powershell
Copy-Item .env.nominatim.example .env.nominatim
```

2. Проверить, что PBF лежит в `data/osm/northwestern-fed-district-latest.osm.pbf`.

3. Поднять сервис:

```powershell
docker compose --env-file .env --env-file .env.nominatim -f docker-compose.yml -f docker-compose.nominatim.yml up -d nominatim
```

4. Дождаться окончания импорта и проверить:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/status
```

5. Для backend указать локальный Nominatim:

```env
NOMINATIM_BASE_URL=http://nominatim:8080
NOMINATIM_MIN_REQUEST_INTERVAL_S=0
NOMINATIM_TIMEOUT_S=10
GEOCODER_ENABLE_FALLBACK=false
```

После изменения `.env` backend нужно перезапустить.

## Быстрый smoke-прогон

Короткая проверка пайплайна и записи отчетов:

```powershell
python scripts/load_test_geocoding.py --requests 20 --concurrency 2
```

Этот режим не включает `force_refresh`, поэтому часть адресов может прийти из кэша.
Для безопасной проверки только по известному кэшу можно передать адресы явно:

```powershell
python scripts/load_test_geocoding.py --requests 20 --concurrency 2 --address "Малая Посадская 13" --address "Пионерская 21"
```

## Честный прогон локального Nominatim

После импорта данных:

```powershell
python scripts/load_test_geocoding.py --requests 200 --concurrency 4 --force-refresh --default-city "Санкт-Петербург"
```

Скрипт откажется запускать `--force-refresh`, если backend указывает на публичный `nominatim.openstreetmap.org`. Это защита от случайного нагрузочного теста внешнего сервиса.

## Что смотреть

Отчеты сохраняются в `reports/load/`:

- `geocoding-load-*.json` - сводка, системные сэмплы и Docker-сэмплы.
- `geocoding-load-requests-*.csv` - каждый HTTP-запрос с latency/status/source/provider.
- `geocoding-load-docker-*.csv` - `docker stats` по контейнерам.

Ключевые метрики:

- `requests_per_second`
- `latency_ms.p95`
- `geocoding_statuses`
- `system.max_cpu_percent`
- `system.max_memory_percent`
- `docker.osm_nominatim.max_cpu_percent`
- `docker.osm_nominatim.max_memory_used_bytes`
- `docker.osm_route_db.max_memory_used_bytes`

Для MVP стоит начать с `--concurrency 2`, затем `4`, затем `8`. Если p95 резко растет, CPU Nominatim держится около 100%, а PostgreSQL активно пишет на диск, текущий лимит параллельных геокодирований нужно оставить ниже последней стабильной ступени.
