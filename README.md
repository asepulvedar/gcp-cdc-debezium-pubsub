# CDC Postgres → Google Pub/Sub Demo

End-to-end example that captures changes from a PostgreSQL table using Debezium Server and republishes them to a Google Cloud Pub/Sub topic. The repository contains everything needed to stand up the stack with Docker, seed demo data, and inspect the resulting change events—ideal as a runnable companion for a Medium article or conference talk.

## Architecture

- **PostgreSQL** (Docker) hosts the `inventory.orders` table and is configured for logical replication.
- **Debezium Server** tails the Postgres WAL, transforms the events, and sinks them directly to Google Pub/Sub via the official connector.
- **Google Pub/Sub** receives the CDC events on a topic that you can subscribe to with any downstream consumer.
- **Python helper** (`read_pubsub_events.py`) provides a quick way to pull and print the events from a Pub/Sub subscription.

```
PostgreSQL ──> Debezium Server ──> Pub/Sub Topic ──> Your Consumers
```

## Prerequisites

1. **Docker & Docker Compose** – Docker Desktop or engine 20.10+ with Compose V2.
2. **Google Cloud project** – with billing enabled.
3. **Service account** – grant at minimum:
   - `roles/pubsub.publisher`
   - `roles/pubsub.subscriber`
   - optionally `roles/pubsub.admin` if you want Debezium to auto-create topics.
4. **Service account key** – JSON key downloaded for the previous account.
5. **gcloud CLI** – for Pub/Sub admin commands.
6. **Python 3.10+** – to run the helper script (virtualenv recommended).

## Repository Layout

```
├─ debezium/
│  ├─ conf/
│  │  ├─ application.properties # Debezium Server configuration
│  │  └─ key.json               # Place your service-account key here (ignored by git)
│  ├─ data/                     # Debezium offset & history files (bind-mounted)
│  └─ docker-compose.yaml       # Orchestration of Postgres + Debezium containers
├─ configure-database.sh        # Seeds Postgres with demo data
├─ create-topic-subscription.sh # Helper to create Pub/Sub topic + subscription
└─ read_pubsub_events.py        # Simple Pub/Sub subscriber to inspect events
```

## One-time Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/asepulvedar/gcp-cdc-debezium-pubsub.git
   cd gcp-cdc-debezium
   ```
2. **Drop credentials**
   - Save the service-account key as `debezium/conf/key.json`.
   - Ensure the file is not world-readable:
     ```bash
     chmod 600 debezium/conf/key.json
     ```
3. **Set the project ID**
   - Edit `debezium/docker-compose.yaml` and replace `alan-sandbox-393620` with your project ID.
   - Optionally adjust the Postgres credentials if needed (they default to `postgres/postgres`).
4. **Review topic naming**
   - Debezium publishes one Pub/Sub topic per captured table using the pattern `{prefix}.{server}.{schema}.{table}`.
   - The default configuration sets `prefix=cdc` and the `inventory.orders` table streams to `cdc.inventory.orders`.
   - If you enable CDC for additional tables, create the matching topics upfront (or allow Debezium to auto-create them as described below).

## Create Pub/Sub Infrastructure

### Option A – Manual creation (recommended for clarity)

```bash
gcloud pubsub topics create cdc.inventory.orders
gcloud pubsub subscriptions create cdc.inventory.orders.sub --topic=cdc.inventory.orders
```

Repeat the commands for every table you enable in CDC (changing only the table suffix). Adjust the names if you customized the topic prefix or server name.

### Option B – Let Debezium create topics

Add the line below to `debezium/conf/application.properties`:

```
debezium.sink.pubsub.create.topics=true
```

The service account now needs at least `pubsub.topics.create`. Debezium will create the topic lazily the first time it publishes an event.

## Run the Demo

1. **Start services**
   ```bash
   cd debezium
   docker compose up -d
   docker compose logs -f debezium   # optional: watch start-up progress
   ```
   Wait until you see messages such as `Snapshot completed`.

2. **Seed the database**
   ```bash
   cd ..
   ./configure-database.sh
   ```
   The script creates `inventory.orders` and inserts a couple of rows to trigger initial CDC events.

3. **Consume events**
   - Install the Pub/Sub client once:
     ```bash
     pip install google-cloud-pubsub
     ```
   - Run the helper:
     ```bash
     export GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/debezium/conf/key.json"
     python read_pubsub_events.py \
       --project-id <your-project> \
       --subscription cdc.inventory.orders.sub
     ```
   - Each message prints the envelope plus metadata. Press `Ctrl+C` to stop; the script acknowledges messages by default (use `--no-ack` to leave them pending).

4. **Trigger more CDC**
   - Desde la terminal:
     ```bash
     docker exec -it $(docker ps -qf name=postgres) \
       psql -U postgres -d postgres \
       -c "INSERT INTO inventory.orders(customer, amount) VALUES ('Charlie', 42.00);"
     ```
   - O usa tu IDE/cliente favorito (DataGrip, DBeaver, TablePlus, psql GUI, etc.) conectándote a `localhost:5432` con `postgres/postgres` para ejecutar inserts o updates manuales.

   Observa el suscriptor en vivo, o tira de la CLI:
   ```bash
   gcloud pubsub subscriptions pull cdc-tutorial-inventory-orders-sub --limit=10 --auto-ack
   ```

   Nota: El ejemplo siguiente usa tanto el prefijo como el nombre de servidor configurados en `cdc`; si conservas el nombre de servidor `tutorial` que trae el repo por defecto, verás `cdc.tutorial.inventory.orders` en tu salida.

   Ejemplo real de lo que imprime `read_pubsub_events.py` (formato completo del envelope Debezium):
   ```
   Message #4
     ID:        16626167246153085
     Published: 2025-10-18 22:25:39.713000+00:00
     Ordering:  {"schema":{"type":"struct","fields":[{"type":"int32","optional":false,"default":0,"field":"id"}],"optional":false,"name":"cdc.inventory.orders.Key"},"payload":{"id":8}}
     Attributes: -
     Data:
   {
     "schema": {
       "type": "struct",
       "fields": [
         {
           "type": "struct",
           "fields": [
             {
               "type": "int32",
               "optional": false,
               "default": 0,
               "field": "id"
             },
             {
               "type": "string",
               "optional": true,
               "field": "customer"
             },
             {
               "type": "bytes",
               "optional": true,
               "name": "org.apache.kafka.connect.data.Decimal",
               "version": 1,
               "parameters": {
                 "scale": "2",
                 "connect.decimal.precision": "10"
               },
               "field": "amount"
             },
             {
               "type": "string",
               "optional": true,
               "name": "io.debezium.time.ZonedTimestamp",
               "version": 1,
               "default": "1970-01-01T00:00:00.000000Z",
               "field": "created_at"
             }
           ],
           "optional": true,
           "name": "cdc.inventory.orders.Value",
           "field": "before"
         },
         {
           "type": "struct",
           "fields": [
             {
               "type": "int32",
               "optional": false,
               "default": 0,
               "field": "id"
             },
             {
               "type": "string",
               "optional": true,
               "field": "customer"
             },
             {
               "type": "bytes",
               "optional": true,
               "name": "org.apache.kafka.connect.data.Decimal",
               "version": 1,
               "parameters": {
                 "scale": "2",
                 "connect.decimal.precision": "10"
               },
               "field": "amount"
             },
             {
               "type": "string",
               "optional": true,
               "name": "io.debezium.time.ZonedTimestamp",
               "version": 1,
               "default": "1970-01-01T00:00:00.000000Z",
               "field": "created_at"
             }
           ],
           "optional": true,
           "name": "cdc.inventory.orders.Value",
           "field": "after"
         },
         {
           "type": "struct",
           "fields": [
             {
               "type": "string",
               "optional": false,
               "field": "version"
             },
             {
               "type": "string",
               "optional": false,
               "field": "connector"
             },
             {
               "type": "string",
               "optional": false,
               "field": "name"
             },
             {
               "type": "int64",
               "optional": false,
               "field": "ts_ms"
             },
             {
               "type": "string",
               "optional": true,
               "name": "io.debezium.data.Enum",
               "version": 1,
               "parameters": {
                 "allowed": "true,last,false,incremental"
               },
               "default": "false",
               "field": "snapshot"
             },
             {
               "type": "string",
               "optional": false,
               "field": "db"
             },
             {
               "type": "string",
               "optional": true,
               "field": "sequence"
             },
             {
               "type": "string",
               "optional": false,
               "field": "schema"
             },
             {
               "type": "string",
               "optional": false,
               "field": "table"
             },
             {
               "type": "int64",
               "optional": true,
               "field": "txId"
             },
             {
               "type": "int64",
               "optional": true,
               "field": "lsn"
             },
             {
               "type": "int64",
               "optional": true,
               "field": "xmin"
             }
           ],
           "optional": false,
           "name": "io.debezium.connector.postgresql.Source",
           "field": "source"
         },
         {
           "type": "string",
           "optional": false,
           "field": "op"
         },
         {
           "type": "int64",
           "optional": true,
           "field": "ts_ms"
         },
         {
           "type": "struct",
           "fields": [
             {
               "type": "string",
               "optional": false,
               "field": "id"
             },
             {
               "type": "int64",
               "optional": false,
               "field": "total_order"
             },
             {
               "type": "int64",
               "optional": false,
               "field": "data_collection_order"
             }
           ],
           "optional": true,
           "name": "event.block",
           "version": 1,
           "field": "transaction"
         }
       ],
       "optional": false,
       "name": "cdc.inventory.orders.Envelope",
       "version": 1
     },
     "payload": {
       "before": null,
       "after": {
         "id": 8,
         "customer": "Roberto",
         "amount": "CV8=",
         "created_at": "2025-10-18T22:25:38.517868Z"
       },
       "source": {
         "version": "2.5.4.Final",
         "connector": "postgresql",
         "name": "cdc",
         "ts_ms": 1760826338518,
         "snapshot": "false",
         "db": "postgres",
         "sequence": "[\"22415064\",\"22416216\"]",
         "schema": "inventory",
         "table": "orders",
         "txId": 753,
         "lsn": 22416216,
         "xmin": null
       },
       "op": "c",
       "ts_ms": 1760826339015,
       "transaction": null
     }
   }
     Action: message acknowledged
   ```

## Customization Ideas

- **Selective capture**: Swap `debezium.source.schema.include.list=inventory` for `debezium.source.table.include.list=inventory.orders` if you only need one table.
- **Connector options**: Adjust snapshot mode, topic prefix, converters, etc., directly in `debezium/conf/application.properties`.
- **Metrics**: The Debezium container exposes metrics on `localhost:8080/metrics` (Prometheus format) if you need observability during demos.
- **Schema evolution**: Alter the `inventory.orders` table and watch how Debezium emits schema change events.

## Troubleshooting

- `NOT_FOUND: Resource not found`: The Pub/Sub topic or subscription is missing; create it or enable auto-creation.
- `PERMISSION_DENIED`: Validate the service account permissions and `GOOGLE_APPLICATION_CREDENTIALS` path inside the container (`docker compose exec debezium env | grep GOOGLE`).
- Debezium stopped unexpectedly: check `docker compose logs debezium` for the underlying exception (topic missing, network errors, etc.).
- Stale offsets: Delete the contents of `debezium/data/` (offset and history files) if you need a clean re-snapshot (the directory is bind-mounted to persist state).


Repite la eliminación para cada tópico y suscripción adicional que hayas creado por tabla.

## License

This project is licensed under the [Apache License 2.0]

## GitHub Topics

`google-cloud` · `debezium` · `pubsub` · `cloud-run` · `change-data-capture` · `data-engineering` · `event-driven` · `docker` · `python`
